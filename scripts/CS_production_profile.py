"""
Created on 09.08.2024

@author: Teemu Hynnä
"""

# Imports
import pandas as pd
import datetime
from pvlib import pvsystem
from pvlib import location
from pvlib import modelchain
from pvlib import irradiance
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS as PARAMS
from pvlib.location import Location
from pvlib.bifacial.pvfactors import pvfactors_timeseries
from gooey import Gooey, GooeyParser
import tkinter
from tkinter import filedialog
import warnings
import matplotlib.pyplot as plt

# supressing shapely warnings that occur on import of pvfactors
warnings.filterwarnings(action='ignore', module='pvfactors')

# Temporary universal parameters
TIMEZONE = "Etc/GMT-3"

# Functions

def select_month(data : pd.DataFrame, 
                 month : int
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
              tmy_data : pd.DataFrame,
              axis_tilt = 90, 
              axis_azimuth = 90, 
              gcr : float = 0.35, 
              max_angle = 0, 
              pvrow_height = 0.8, 
              pvrow_width = 7.455, 
              albedo : float = 0.25, 
              bifaciality_factor : float = 0.9, 
              timezone : str = TIMEZONE, 
              latitude : float = 60.455, 
              longitude : float = 22.286, 
              date_start : str = '2020-06-01', 
              date_end : str = '2020-07-01',
              frequency : str = '1H'
              ) -> pd.DataFrame:
    
    """
    Calculates the effective irradiance on given PV setup and location. Effective irradiance  is calculated as (E_eff = E_front + E_rear * bifaciality_factor).

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
    tz=TIMEZONE
    lat, lon= latitude, longitude
    date_start= date_start
    date_end=date_end
    
    # Define time characteristics
    times = pd.date_range(date_start, date_end, tz=tz, freq='1H')
    times = times[:-1]
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
        irrad_effective['total_abs_front'] + (irrad_effective['total_abs_back']) * bifaciality_factor
    )

    return irrad_effective


def power_production(
                    leap_year,
                    tmy_data : pd.DataFrame,
                    axis_tilt = 90, 
                    axis_azimuth = 90, 
                    gcr : float = 0.35, 
                    max_angle = 0, 
                    pvrow_height = 0.8, 
                    pvrow_width = 7.455, 
                    albedo : float = 0.25, 
                    bifaciality_factor : float = 0.9, 
                    timezone : str = TIMEZONE, 
                    latitude : float = 60.455, 
                    longitude : float = 22.286, 
                    date_start : str = '2020-06-01', 
                    date_end : str = '2020-07-01',
                    frequency : str = '1H'
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
    array = pvsystem.Array(mount = sat_mount,
                        module_parameters=cec_module,
                        temperature_model_parameters=temp_model_parameters)

    # Create system object
    system = pvsystem.PVSystem(arrays=[array],
                            inverter_parameters=cec_inverter)

    # ModelChain requires the parameter aoi_loss to have a value. pvfactors
    # applies surface reflection models in the calculation of front and back
    # irradiance, so assign aoi_model='no_loss' to avoid double counting
    # reflections.
    site_location = location.Location(latitude, longitude, tz=timezone, altitude=30)
    mc_bifi = modelchain.ModelChain(system, site_location, aoi_model='no_loss', name='bifacial')
    mc_bifi.run_model_from_effective_irradiance(irrad_effective)
    print(mc_bifi)

    return mc_bifi.results.ac


def plot_results(data):
    #TODO: plotting of multiple results.
    hours = data.index.strftime('%H:%M:%S')
    data2 = data.groupby(hours).mean()

    fig, (ax1, ax2) = plt.subplots(1,2)
    data.plot(ax=ax1); ax1.set_title('Full month')
    data2.plot(ax=ax2); ax2.set_title('Average profile of the month')
    #TODO: Create more sophisticated way of reading x-ticks from the data.
    ax2.set_xticks(range(25), ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "00"])
    plt.show()

    return


def save_results(data):
    #TODO: save the results in the wanted format.
    #TODO: Save also metadata and create automatically a folder for them with ISO8061 format.
    tkinter.Tk().withdraw() # Prevents an empty tkinter window from appearing.

    file_name = filedialog.asksaveasfilename()

    if file_name:
        data.to_csv(f"{file_name}.csv", header=["AC Power (W)"], index_label="Time")

    return


@Gooey
def main():
    #TODO: add on runtime checks that the user inputs are of correct type.
    parser = GooeyParser(description="TMY production profile modeller")
    parser.add_argument('Latitude', action="store")
    parser.add_argument('Longitude', action="store")
    parser.add_argument('Plot_results', choices=["Yes", "No"])
    parser.add_argument('Save_results', choices=["Yes", "No"])
    #parser.add_argument('Timezone', action='count')

    args = parser.parse_args()

    leap = False

    loc = Location(float(args.Latitude), float(args.Longitude), tz=TIMEZONE, altitude=30)
    times = pd.date_range(start='2013-01-01', end='2014-01-01', tz=loc.tz, freq='1H')
    times = times[:-1]
    df_cs = loc.get_clearsky(times)
    plt.plot(df_cs[34560:36000])
    plt.show()

    # Get number of month based on the selection made by user.
    months= {"January" : 1, "February" : 2, "March" : 3, "April" : 4, "May" : 5, "June" : 6, "July" : 7, "August" : 8, "September" : 9, "October" : 10, "November" : 11, "December" : 12}
    #month_no = months.get(args.Month)
    # Then select a slice of the tmy dataset for that specific month

    for month in months:
        month_no = months.get(month)
        df_month = select_month(df_cs, month_no)
        print(df_month)
        # Let's take the start and end dates from the data so there is less parameters for user.
        print(df_month)
        date_start = df_month.iloc[20].name.strftime('%Y-%m-%d') # we take the 4th element as we have shifted by three hours and the years change in TMY. We just need Y-m-d so hours don't matter here.
        # df_month = df_month[~((df_month.index.month == 3) & (df_month.index.day == 1) & (df_month.index.hour < TIMEZONE))] # Again a sort of brute force fix for march bug
        # Again here some extra effort to work with leap days as the TMY data does not have them.
        date_end = df_month.iloc[-23].name + datetime.timedelta(hours=23)
        date_end = date_end.strftime('%Y-%m-%d')
        print(date_start, date_end)

        results = power_production(leap_year = leap, tmy_data=df_month, date_start=date_start, date_end=date_end, timezone=loc.tz, latitude=float(args.Latitude), longitude=float(args.Longitude))

        # Plot results if so wanted
        if args.Plot_results == "Yes":
            plot_results(results)
        
        # Save results if so wanted
        if args.Save_results == "Yes":
            save_results(results) # TODO: Fix save_results so that it works with one or two files.


    return

main()