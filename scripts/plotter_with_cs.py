import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import tkinter
from tkinter import filedialog

def plot_avgs(oulu, turku, berlin, munchen, rome, catania, oulu_cs, turku_cs, berlin_cs, munchen_cs, rome_cs, catania_cs):
    sns.set_theme(context='paper',style='darkgrid')
    locations = [oulu, turku, berlin, munchen, rome, catania, oulu_cs, turku_cs, berlin_cs, munchen_cs, rome_cs, catania_cs]
    legends = ['March_FMI', 'April_FMI', 'May_FMI', 'June_FMI', 'July_FMI', 'August_FMI', 'March_CS', 'April_CS', 'May_CS', 'June_CS', 'July_CS', 'August_CS']
    palette = sns.color_palette("coolwarm", int(len(locations)/2)).as_hex()
    
    my_dpi = 144
    plt.figure(figsize=(800/my_dpi, 600/my_dpi), dpi=my_dpi)

    for i, loc in enumerate(locations):    
        loc['Time'] = pd.to_datetime(loc['Time']).dt.strftime('%H:%M:%S')
        hours = loc['Time']
        data = loc.groupby(hours).mean()
        data = data.rename(columns={"AC Power (W)" : legends[i]})
        if (i < 6):
            sns.lineplot(data=data[legends[i]], color=palette[i], label=legends[i], linewidth=2)
        else:
            sns.lineplot(data=data[legends[i]], color=palette[i-6], label=legends[i], linewidth=2, linestyle='dashed')

    plt.xlabel('Hours')
    plt.ylabel('AC Power (W)')
    plt.title('Average daily production profile in Mar-Aug from FMI and PVGIS TMY data')
    plt.xticks(ticks=['00:00:00', '01:00:00', '02:00:00', '03:00:00', '04:00:00', '05:00:00', '06:00:00', '07:00:00', '08:00:00', '09:00:00', '10:00:00', '11:00:00', '12:00:00', '13:00:00', '14:00:00', '15:00:00', '16:00:00', '17:00:00', '18:00:00', '19:00:00', '20:00:00', '21:00:00', '22:00:00', '23:00:00'], labels=['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23'])
    #plt.locator_params(axis='x', nbins=6)
    plt.legend()
    plt.show()
    
    return

def open_data() -> pd.DataFrame:
    # Ask the user to select data from the file explorer
    tkinter.Tk().withdraw() # Prevents an empty tkinter window from appearing.

    file_path = filedialog.askopenfilename()

    data = pd.read_csv(file_path)

    return data

def main():
    locations = []
    for i in range(12):
        data = open_data()
        locations.append(data)
    print(locations)
    x, y, z, i, j, k, x2, y2, z2, i2, j2, k2, = locations
    plot_avgs(oulu=x, turku=y, berlin=z, munchen=i, rome=j, catania=k, oulu_cs=x2, turku_cs=y2, berlin_cs=z2, munchen_cs=i2, rome_cs=j2, catania_cs=k2)
    return

main()