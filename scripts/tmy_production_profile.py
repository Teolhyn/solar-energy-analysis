"""
Created on 15.05.2024

@author: Teemu Hynnä
"""

# Imports
import io
import datetime
import tkinter
from tkinter import filedialog
import warnings
import pandas as pd
import requests
from pvlib import pvsystem
from pvlib import location
from pvlib import modelchain
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS as PARAMS
from pvlib.bifacial.pvfactors import pvfactors_timeseries
from gooey import Gooey, GooeyParser
import matplotlib.pyplot as plt

# supressing shapely warnings that occur on import of pvfactors
warnings.filterwarnings(action='ignore', module='pvfactors')


# Temporary universal parameters
TIMEZONE = 3

# Functions


def read_data(
    datetimeformat: str = r'%Y-%m-%d %H:%M:%S',
    datetimeindex: int = 0,
    ghi_index: int = 5,
    dhi_index: int = 6,
    dni_index: int = 7
) -> pd.DataFrame:
    """
    Reads user input and generates a pandas dataframe from user selected data. This function
    should understand different formats and should ask for user input for columns. 

    Args:
        datetimeformat (str): Datetime format, e.g. "%Y-%m-%d:%H%M".
        datetimeindex (int): Column index of datetime data.
        ghi_index (int): Column index of GHI data.
        dhi_index (int): Column index of DHI data.
        dni_index (int): Column index of DNI data.

    Returns:
        pd.DataFrame: Pandas DataFrame with TMY data containing dateTimeIndex, ghi, dhi, and dni columns.
    """
    # TODO: Add possible Tamb etc. data that might be needed.

    # Ask the user to select data from the file explorer
    tkinter.Tk().withdraw()  # Prevents an empty tkinter window from appearing.

    file_path = filedialog.askopenfilename()

    # Split the file path from '.' to get the extension (type)
    extension = file_path.split('.', 1)

    # Create a dataframe from the selected data file.
    if extension == '.json':
        dataframe = pd.read_json(file_path)
    if extension in ['.xls', '.xlsx', '.xlsm', '.xlsb', '.odf', '.ods', '.odt']:
        dataframe = pd.read_excel(file_path)
    else:
        dataframe = pd.read_csv(file_path)

    # Rename the needed data columns in to the pvlib format
    dataframe.columns.values[datetimeindex] = "dt"
    dataframe.columns.values[ghi_index] = "ghi"
    dataframe.columns.values[dhi_index] = "dhi"
    dataframe.columns.values[dni_index] = "dni"

    # Restructure the data to include only needed data for the simulation
    data = dataframe.iloc[:, [datetimeindex, ghi_index, dhi_index, dni_index]]

    # Surpress a settingWithCopy warning, as it works here. (row below the pd.options..)
    pd.options.mode.chained_assignment = None
    # define 'dt' as datetimeindex and reformat to pandas datetime
    data['dt'] = pd.to_datetime(data['dt'], format=datetimeformat)
    data = data.set_index(['dt'])

    return data


def read_data_api(lat, lon):
    url = f"https://re.jrc.ec.europa.eu/api/v5_2/tmy?lat={lat}&lon={lon}&outputformat=basic"
    r = requests.get(url)
    df = pd.read_csv(io.StringIO(r.text))

    df.columns.values[0] = "dt"
    df.columns.values[3] = "ghi"
    df.columns.values[5] = "dhi"
    df.columns.values[4] = "dni"

    data = df.iloc[:, [0, 3, 5, 4]]

    # Surpress a settingWithCopy warning, as it works here. (row below the pd.options..)
    pd.options.mode.chained_assignment = None
    # define 'dt' as datetimeindex and reformat to pandas datetime
    data['dt'] = pd.to_datetime(data['dt'], format=r'%Y%m%d:%H%M')
    data = data.set_index(['dt'])
    # Was shifted by 3 hours but creates problems with multiple years in TMY
    # TODO: The amount to shift is dependent on the timezone of the location. (E.g. you shift 3 hours if GMT+3.) This need to be done so that it checks the timezone from location and time of year.
    data.index = data.index.shift(TIMEZONE, freq='H')
    # Remove leap days that can be caused by shifting the data in February.
    # TMY data does not have the leap days.
    data = data[~((data.index.month == 2) & (data.index.day == 29))]
    print(data)

    url = f"https://re.jrc.ec.europa.eu/api/v5_2/tmy?lat={lat}&lon={lon}&outputformat=json"
    r = requests.get(url, timeout=20)
    data_raw = pd.read_json(io.StringIO(r.text))

    return data, data_raw


def select_month(data: pd.DataFrame,
                 month: int
                 ) -> pd.DataFrame:
    """
    Select a single month of the whole TMY dataset.

    Args:
        data (pd.DataFrame): whole year of TMY data.
        month (int): number of the month wanted to select, e.g. '6' for June.

    Returns:
        pd.DataFrame: Subset of the original TMY dataset for the selected month.
    """
    month_data = data[data.index.month == month]

    return month_data


def effective_irradiance(
    leap_year,
    tmy_data: pd.DataFrame,
    axis_tilt=90,
    axis_azimuth=90,
    gcr: float = 0.35,
    max_angle=0,
    pvrow_height=0.8,
    pvrow_width=7.455,
    albedo: float = 0.25,
    bifaciality_factor: float = 0.9,
    timezone: str = f'Etc/GMT-{TIMEZONE}',
    latitude: float = 60.455,
    longitude: float = 22.286,
    date_start: str = '2020-06-01',
    date_end: str = '2020-07-01',
    frequency: str = '1H'
) -> pd.DataFrame:
    """
    Calculates the effective irradiance on given PV setup and location. 
    Effective irradiance  is calculated as (E_eff = E_front + E_rear * bifaciality_factor).

    Args:
        axis_tilt (int|float): something.
        axis_azimuth (int|float): something.
        ground_coverage_ratio (float): something.
        max_angle (int|float):  something.
        pvrow_height (int|float):  something.
        pvrow_width (int|float): something.
        albedo (float): something.
        bifaciality_factor (float): Bifaciality factor. Default value is 0.9.
        timezone (str):  Timezone of simulated location
        latitude (float): Latitude of the simulated location.
        longitude (float): Longitude of the simulated location.
        date_start (str):  Datetime of the first datapoint.
        date_end (str): Datetime of the last datapoint.
        frequency (str): Frequency of datapoints. Default is one hour ('1H').

    Returns:
        pd.DataFrame: Dataframe of effective irradiance on the solar panel.
    """

    # Location params
    tz = timezone
    lat, lon = latitude, longitude

    # Define time characteristics
    times = pd.date_range(date_start, date_end, tz=tz, freq=frequency)
    times = times[:-1]
    print("Is leap year:", leap_year)
    if leap_year:
        # Remove leap days in case there are any as the TMY data does not have them.
        times = times[~((times.month == 2) & (times.day == 29))]
        # Brute force fix for the March bug caused by shifting and the previous day being leap day. #NOTE comment or uncomment this line if you get array size not matching error!
        times = times[~((times.month == 3) & (
            times.day == 1) & (times.hour < TIMEZONE))]
    print(times)

    # Define location
    site_location = location.Location(lat, lon, tz=tz, altitude=30)

    # Calculate solar positions
    solar_position = site_location.get_solarposition(times)

    # Calculate irradiance with pvfactors
    irrad = pvfactors_timeseries(solar_position['azimuth'],
                                 solar_position['apparent_zenith'],
                                 90,
                                 90,
                                 axis_azimuth,
                                 times,
                                 tmy_data['dni'],
                                 tmy_data['dhi'],
                                 gcr,
                                 pvrow_height,
                                 pvrow_width,
                                 albedo,
                                 n_pvrows=1,
                                 index_observed_pvrow=0
                                 )

    irrad_effective = pd.concat(irrad, axis=1)

    irrad_effective['effective_irradiance'] = (
        irrad_effective['total_abs_front'] +
        (irrad_effective['total_abs_back']) * bifaciality_factor
    )

    return irrad_effective


def power_production(
    leap_year,
    tmy_data: pd.DataFrame,
    axis_tilt=90,
    axis_azimuth=90,
    gcr: float = 0.35,
    max_angle=0,
    pvrow_height=0.8,
    pvrow_width=7.455,
    albedo: float = 0.25,
    bifaciality_factor: float = 0.9,
    timezone: str = f'Etc/GMT-{TIMEZONE}',
    latitude: float = 60.455,
    longitude: float = 22.286,
    date_start: str = '2020-06-01',
    date_end: str = '2020-07-01',
    frequency: str = '1H'
):

    irrad_effective = effective_irradiance(
        leap_year,
        tmy_data,
        axis_tilt,
        axis_azimuth,
        gcr,
        max_angle,
        pvrow_height,
        pvrow_width,
        albedo,
        bifaciality_factor,
        timezone,
        latitude,
        longitude,
        date_start,
        date_end,
        frequency)

    # Load solar position and tracker orientation for use in pvsystem object
    sat_mount = pvsystem.SingleAxisTrackerMount(axis_tilt=axis_tilt,
                                                axis_azimuth=axis_azimuth,
                                                max_angle=max_angle,
                                                backtrack=False,
                                                gcr=gcr)

    # Load temperature parameters and module/inverter specifications
    temp_model_parameters = PARAMS['sapm']['open_rack_glass_glass']
    sandia_modules = pvsystem.retrieve_sam('SandiaMod')
    cec_modules = pvsystem.retrieve_sam('CECMod')
    cec_module = cec_modules['Prism_Solar_Technologies_Bi60_375BSTC']
    cec_inverters = pvsystem.retrieve_sam('cecinverter')
    cec_inverter = cec_inverters['ABB__MICRO_0_25_I_OUTD_US_208__208V_']

    # DC arrays
    array = pvsystem.Array(mount=sat_mount,
                           module_parameters=cec_module,
                           temperature_model_parameters=temp_model_parameters)

    # Create system object
    system = pvsystem.PVSystem(arrays=[array],
                               inverter_parameters=cec_inverter)

    # ModelChain requires the parameter aoi_loss to have a value. pvfactors
    # applies surface reflection models in the calculation of front and back
    # irradiance, so assign aoi_model='no_loss' to avoid double counting
    # reflections.
    site_location = location.Location(
        latitude, longitude, tz=timezone, altitude=30)
    mc_bifi = modelchain.ModelChain(
        system, site_location, aoi_model='no_loss', name='bifacial')
    mc_bifi.run_model_from_effective_irradiance(irrad_effective)
    print(mc_bifi)

    return mc_bifi.results.ac


def plot_results(data):
    # TODO: plotting of multiple results.
    hours = data.index.strftime('%H:%M:%S')
    data2 = data.groupby(hours).mean()

    fig, (ax1, ax2) = plt.subplots(1, 2)
    data.plot(ax=ax1)
    ax1.set_title('Full month')
    data2.plot(ax=ax2)
    ax2.set_title('Average profile of the month')
    # TODO: Create more sophisticated way of reading x-ticks from the data.
    ax2.set_xticks(range(25), ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
                   "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "00"])
    plt.show()

    return


def save_results(data, raw):
    # TODO: save the results in the wanted format.
    # TODO: Save also metadata and create automatically a folder for them with ISO8061 format.
    tkinter.Tk().withdraw()  # Prevents an empty tkinter window from appearing.

    file_name = filedialog.asksaveasfilename()

    if file_name:
        data.to_csv(f"{file_name}.csv", header=[
                    "AC Power (W)"], index_label="Time")
        raw.to_json(f"{file_name}.json")

    return


@Gooey
def main():
    # TODO: add on runtime checks that the user inputs are of correct type.
    parser = GooeyParser(description="TMY production profile modeller")
    parser.add_argument('Use_API', choices=["Yes", "No"])
    parser.add_argument('Month', choices=["January", "February", "March", "April",
                        "May", "June", "July", "August", "September", "October", "November", "December"])
    parser.add_argument('Latitude', action="store")
    parser.add_argument('Longitude', action="store")
    parser.add_argument('Plot_results', choices=["Yes", "No"])
    parser.add_argument('Save_results', choices=["Yes", "No"])
    # parser.add_argument('Timezone', action='count')

    args = parser.parse_args()

    leap = False

    # Depending on if 'Use_API' either use API or ask for datafile
    if args.Use_API == "Yes":
        print("Connecting to PVGIS...")
        df, raw = read_data_api(args.Latitude, args.Longitude)
        print("Data collected from PVGIS succesfully!")
    else:
        print("Manual data selection selected. Please select your TMY data.")
        df = read_data()
        print("Data loaded succesfully!")

    # Get number of month based on the selection made by user.
    months = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
              "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}
    # month_no = months.get(args.Month)
    # Then select a slice of the tmy dataset for that specific month
    for month in months:
        month_no = months.get(month)
        df_month = select_month(df, month_no)
        # Let's take the start and end dates from the data so there is less parameters for user.
        print(df_month)
        if month == "January" and TIMEZONE != 0 and args.Use_API == "Yes":
            df_temp = df_month.tail(TIMEZONE)
            df_month = df_month[:-TIMEZONE]
            df_month = pd.concat([df_temp, df_month])
        print(df_month)
        # we take the 4th element as we have shifted by three hours and the years change in TMY. We just need Y-m-d so hours don't matter here.
        date_start = df_month.iloc[20].name.strftime('%Y-%m-%d')
        # df_month = df_month[~((df_month.index.month == 3) & (df_month.index.day == 1) & (df_month.index.hour < TIMEZONE))] # Again a sort of brute force fix for march bug
        # Again here some extra effort to work with leap days as the TMY data does not have them.
        if df_month.index[5].is_leap_year:
            leap = True
            date_end = df_month.iloc[-1].name + datetime.timedelta(hours=23)
        else:
            date_end = df_month.iloc[-23].name + datetime.timedelta(hours=23)
        date_end = date_end.strftime('%Y-%m-%d')
        print(date_start, date_end)

        results = power_production(leap_year=leap, tmy_data=df_month, date_start=date_start,
                                   date_end=date_end, latitude=float(args.Latitude), longitude=float(args.Longitude))

        # Plot results if so wanted
        if args.Plot_results == "Yes":
            plot_results(results)

        # Save results if so wanted
        if args.Save_results == "Yes" and args.Use_API == "Yes":
            save_results(results, raw)
        elif args.Save_results == "Yes" and args.Use_API == "No":
            # TODO: Fix save_results so that it works with one or two files.
            save_results(results)

    return


main()
