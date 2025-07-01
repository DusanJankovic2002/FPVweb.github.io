# -*- coding: utf-8 -*-
"""
Created on Mon Jun 23 15:07:37 2025

@author: dusan
"""

# -*- coding: utf-8 -*-
"""
Created on Thu Apr 24 05:41:50 2025

@author: dusan
"""

import pvlib

    #get country from coordinates
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable



def get_country_from_coords(lat, lon, max_retries=3):
        
        
        geolocator = Nominatim(user_agent="geo_locator")
        
        for attempt in range(max_retries):
            try:
                location = geolocator.reverse((lat, lon), exactly_one=True, language="en")
                if location and 'address' in location.raw:
                    return location.raw['address'].get('country', "Unknown")
                return "Unknown"
            except (GeocoderTimedOut, GeocoderUnavailable) as e:
                if attempt == max_retries - 1:
                    print(f"Error: {e}. Max retries reached.")
                    return "Unknown"
                continue
            except Exception as e:
                print(f"Unexpected error: {e}")
                return "Unknown"

latitude =  40
longitude = 25

if __name__ == '__main__':
    country1 = get_country_from_coords(latitude, longitude)
    print(f"Country: {country1}")

    



#api call from pvlib
import pvlib

    
def getPVdata(longitude,latitude):
    pv_data = pvlib.iotools.get_pvgis_hourly(latitude, longitude, start=2020,
    end=2020, raddatabase="PVGIS-SARAH3", components=True, surface_tilt=20, 
    surface_azimuth=0, outputformat='json', usehorizon=True, 
    userhorizon=None, pvcalculation=False, peakpower=None, 
    pvtechchoice='crystSi', mountingplace='free', loss=0, 
    trackingtype=0, optimal_surface_tilt=False, optimalangles=False, 
    url='https://re.jrc.ec.europa.eu/api/', map_variables=True, timeout=30)
    return pv_data

pv_data = getPVdata(longitude,latitude)
df=pv_data[0]
 


    





    

#economics, later to be combined with energy generation to get LCOE
import pandas as pd
import numpy as np
import os

import pandas as pd

def get_economic_data(country_name, file_path=None):
    # If no custom path is given, use the file in the same directory as the script
    if file_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "econFPV2.xlsx")
    
    try:
        df = pd.read_excel(file_path, sheet_name='Sheet1', skiprows=3)
        df.columns = [col.strip() for col in df.columns]
        
        country_data = df[df['Country'].str.strip().str.lower() == country_name.lower()]
        
        if not country_data.empty:
            return {
                'country': country_data['Country'].values[0],
                'day_ahead_avg_price': country_data['DayAVG'].values[0],
                'inflation_rate': country_data['Inflation'].values[0],
                'capex': country_data['capex'].values[0],
                'opex': country_data['opex'].values[0],
                'WACC': country_data['WACC'].values[0],
                'CorpTax': country_data['CorpTax'].values[0]
            }
        else:
            print(f"Country '{country_name}' not found in the database.")
            return None
            
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None
    
    
    

if __name__ == '__main__':
   
    economic_data = get_economic_data(country1)
    print(economic_data)  # Or do something with the data
           
   
   
    


years = 20
systemSize = 100
def totalcost():
    return capex*(((1+inflation/100)**21 - 1)/((1+inflation/100)-1))
    


#extra econ to be modified with the stuff

#saving all variables that can be used for LCOE calculation, !!ADD DISCOUNT RATE, CORP TAX, WACC, DEPRECIATION






#FULL PERFORMANCE ANALYSIS BELOW

dni_extra=1300
#pv performance and energy generation
import pvlib
import numpy as np

t = 1
temp_air = df.iloc[t,4]
wind_speed =  df.iloc[t,5]
altitude = 0
solpos = df.iloc[0,3]
DNI =  df.iloc[0,0]
BNI = df.iloc[0,1]
GHI =  BNI + DNI
area = 1000
eff = 20
r = 0.5
tilt = 10





tilt = 6
def calculate_yearly_yield(df, latitude, longitude, dni_extra,surface_tilt=tilt, u_c=56, u_v=0, albedo=0.06, 
                          surface_azimuth=180., gamma_pdc=-0.0034, pdc0=1., 
                         p_losses=0.14, inv_eff=0.96, module_efficiency=0.1, alpha_absorption=0.9):
    
    
    pv_data2 = pvlib.iotools.get_pvgis_hourly(latitude, longitude, surface_tilt=tilt, start=2020,
    end=2020, raddatabase="PVGIS-SARAH3", components=True, 
    surface_azimuth=180, outputformat='json', usehorizon=True, 
    userhorizon=None, pvcalculation=False, peakpower=None, 
    pvtechchoice='crystSi', mountingplace='free', loss=0, 
    trackingtype=0, optimal_surface_tilt=False, optimalangles=False, 
    url='https://re.jrc.ec.europa.eu/api/', map_variables=True, timeout=30)
    
    total_power = 0
    df2 = pv_data2[0]
    for t in range(1,8760,1):
        try:
            # Extract values
            DNI = df2.iloc[t, 0]
            BNI = df2.iloc[t, 1]
            zenith = 90-df2.iloc[t, 3]  # Direct zenith angle value
            azimuth = 0  # Direct azimuth angle value
            temp_air = df2.iloc[t, 4]
            wind_speed = df2.iloc[t, 5]
            
            GHI = BNI + DNI
            altitude = 0
            
            # Calculate airmass using direct zenith value
            airmass_relative = pvlib.atmosphere.get_relative_airmass(zenith, model='kastenyoung1989')
            airmass = pvlib.atmosphere.get_absolute_airmass(airmass_relative)
            
            # Calculate angle of incidence
            aoi = pvlib.irradiance.aoi(surface_tilt, surface_azimuth, zenith, azimuth)
            iam = pvlib.iam.physical(aoi)
            
            # Rest of your calculations...
            poa_ground_diffuse = pvlib.irradiance.get_ground_diffuse(surface_tilt, GHI, albedo)
            poa_sky_diffuse = pvlib.irradiance.get_sky_diffuse(
                surface_tilt, surface_azimuth, zenith, azimuth, 
                BNI, GHI, DNI, dni_extra, airmass=airmass, 
                model='isotropic')
            poa = pvlib.irradiance.poa_components(aoi, BNI, poa_sky_diffuse, poa_ground_diffuse)
             # Access as dictionary key
            poa_direct = poa['poa_direct']
            poa_diffuse = poa['poa_diffuse']
            poa_global = poa['poa_global']
           
            temp_cell = pvlib.temperature.pvsyst_cell(
                poa['poa_global'], temp_air, wind_speed, u_c, u_v, 
                module_efficiency, alpha_absorption=alpha_absorption)
            
            g_poa_effective =  poa['poa_direct']* iam + poa['poa_diffuse']
            pv_yield = pvlib.pvsystem.pvwatts_dc(g_poa_effective, temp_cell, pdc0, gamma_pdc, temp_ref=25.0)
            
            total_power += pv_yield * inv_eff * (1 - p_losses)
            
        except Exception as e:
            print(f"Error at hour {t}: {str(e)}")
            continue
    
    return total_power
if __name__ == '__main__':
    total_yearly_power = calculate_yearly_yield(df, latitude, longitude, dni_extra)
    print(f"total yearly power is {total_yearly_power} kWh/kW")






#FULL ECONOMIC ANALYSIS BELOW
if __name__ == '__main__':
    econ = pd.read_excel("econFPV2.xlsx", engine="openpyxl")
    day_ahead_avg_price = economic_data['day_ahead_avg_price']  
    inflation = economic_data['inflation_rate']
    country_name = economic_data['country']
    opex = economic_data['opex']
    capex = economic_data['capex']
    dr = economic_data['WACC']
    Tx = economic_data['CorpTax']



'''if __name__ == '__main__':
    print(capex)
    print(opex)
    print(inflation)
    print(country_name)
    print(dr)
    print(Tx)'''
    


# Display the first few rows of the table

econ = pd.read_excel("econFPV2.xlsx")
def calculate_lcoe(Ef, T=25, deg=0.01, Nd=20):
    
    #Calculating Annual Tax Depreciation
    Dn=capex/Nd
    #Setting Values of Numerator and Denominator before Year 1
    lcoe_num=capex
    lcoe_den=0
    #Iteration over the PV system lifetime
    for year in np.arange(1,T+1):
        #Add the yearly OPEX costs to numerator
        lcoe_num+=opex*(1-Tx/100)*(1+inflation/100)**year/(1+dr/100)**year
        #Substract the depreciation from numerator
        if year<=Nd: lcoe_num-=(Dn*Tx/100)/(1+dr/100)**year
        #Add the yearly yield, after degradation, to denominator
        lcoe_den+=(Ef*(1-deg)**year)/(1+dr/100)**year    
    #Return the value of the ratio between numerator and denominator
    return lcoe_num/lcoe_den


if __name__ == '__main__':
    lcoe = calculate_lcoe(total_yearly_power)

    print(f"lcoe is {lcoe}")


NPVtotal=0
def calculate_npv(capex,opex,NPVtotal,T,taxBenefit=0):
    
    for T in range(1,25,1):
       
        revenue = day_ahead_avg_price * total_yearly_power/1000
        cashflow = (revenue*(1-Tx/100) - opex)
        discountedCF = (revenue*(1-Tx/100) - opex)/(1+dr/100)**T
        if NPVtotal>0:
            payback=capex/cashflow
    
        NPVtotal += discountedCF
        NPV2 = (revenue*(1-Tx/100) - opex)/(1+dr/100)**25
        
    return NPVtotal,revenue,capex,opex,Tx,dr,NPV2,payback

def calculateqqqqqqq_irr():
    factor = (1-((1/(1+dr/100))**26))/(1-(1/(1+dr/100))) -1
    cashflow = (((day_ahead_avg_price * total_yearly_power/1000)*(1-Tx/100)) - opex)
    ratio = capex/cashflow 
    return ratio,factor


if __name__ == '__main__':
    print(calculateqqqqqqq_irr())

    print(calculate_npv(capex,opex,0,25,NPVtotal))

    print(GHI,DNI,BNI,wind_speed,temp_air,solpos) 
  
   


#when testing, approximately you need a cash flow of 120 per year per kw to sustain the discount rate fo croatia
cashflow = 250
from scipy.optimize import fsolve

def solve_irr(capex, cashflow, years, tol=1e-6, max_iter=100):
    low = 0.00001
    high = 1.0
    for _ in range(max_iter):
        mid = (low + high) / 2
        npv = sum(cashflow / (1 + mid) ** t for t in range(1, years + 1))
        if abs(npv - capex) < tol:
            return mid
        if npv > capex:
            low = mid
        else:
            high = mid
    raise ValueError("IRR did not converge")
    
if __name__ == '__main__':
    irr = solve_irr(capex, cashflow, 25)
    print(irr)


def calculate_dcf(capex, cashflow, dr):
    
    cumulative_pv = 0.0
    year = 0
    
    while cumulative_pv < capex:
        year += 1
        pv = cashflow / ((1 + dr/100) ** year)
        cumulative_pv += pv

        if cumulative_pv >= capex:
            # Backtrack to find the exact year fraction
            cumulative_pv -= pv
            remaining = capex - cumulative_pv
            fraction = remaining / pv
            return year - 1 + fraction

        if year > 1000:  # To prevent infinite loops
            return None

    return year
if __name__ == '__main__':
    dcf = calculate_dcf(capex, cashflow,dr)
    print(dcf)


#here put a for loop for each time from t=1 to t=8760, we have variables iloc[t,column] then the function calculate_yield 
#is looped for each value of t. then we take into account the variable SUM = 0 of the total power generated
#using this, we put SUM += SUM , to keep adding the power calculated until t=8760. This is the total generated power