from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import pvlib
from scipy.optimize import fsolve
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import pandas as pd
import os
import numpy as np

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    session.clear()
    return render_template('mybe2.html')

@app.route('/submit', methods=['POST'])
def handle_submission():
    try:
        if not request.form:
            return jsonify({'error': 'No form data received'}), 400

        required_fields = ['longitude', 'latitude', 'system-size']
        for field in required_fields:
            if field not in request.form:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Initialize session data dictionaries if they don't exist
        if 'form_data' not in session:
            session['form_data'] = {}
        if 'results' not in session:
            session['results'] = {}

        # Get country and economic data first
        longitude = float(request.form['longitude'])
        latitude = float(request.form['latitude'])
        country = get_country_from_coords(latitude, longitude)
        economic_data = get_economic_data(country) or {}

        # Process form data with economic data as defaults
        form_data = {
            'location_method': request.form.get('location_method', 'coordinates'),
            'longitude': longitude,
            'latitude': latitude,
            'system_size': float(request.form['system-size']),
            'tilt_angle': float(request.form.get('tilt-angle', 10)),
            'years': int(request.form.get('years', 25)),
            'system_loss': float(request.form.get('system-loss', 14)),
            'panel_efficiency': float(request.form.get('panel-efficiency', 10)),
            'degradation_rate': float(request.form.get('degradation-rate', 0.75)),
            'azimuth': int(request.form.get('azimuth', 180)),
            'Uv': float(request.form.get('Uv', 0)),
            'Uc': float(request.form.get('Uc', 56)),
            'capex': float(request.form.get('capex', economic_data.get('capex', 1200))),
            'opex': float(request.form.get('opex', economic_data.get('opex', 20))),
            'discount_rate': float(request.form.get('discount-rate', economic_data.get('WACC', 6.5))),
            'inflation_rate': float(request.form.get('inflation-rate', economic_data.get('inflation_rate', 2.5))),
            'day_ahead_avg_price': float(request.form.get('day_ahead_avg_price', economic_data.get('day_ahead_avg_price', 0.15))),
            'corp_tax': float(request.form.get('corp_tax', economic_data.get('CorpTax', 20))),
            'country': country
        }

        # Handle file upload if present
        if 'irradiance-data' in request.files:
            file = request.files['irradiance-data']
            if file.filename != '':
                form_data['irradiance_file'] = {
                    'filename': file.filename,
                    'content_type': file.content_type,
                    'size': len(file.read())
                }
                file.seek(0)

        # Store form data in session
        session['form_data'] = form_data
        session.modified = True

        # Calculate PV data and metrics
        try:
            pv_data = get_pv_data(
                longitude=form_data['longitude'],
                latitude=form_data['latitude'],
                tilt=form_data['tilt_angle'],
                azimuth=form_data['azimuth']
            )
            
            total_yearly_power = calculate_yearly_yield(
                pv_data[0], 
                form_data['latitude'], 
                form_data['longitude'], 
                1300,  # dni_extra
                surface_tilt=form_data['tilt_angle'],
                surface_azimuth=form_data['azimuth']
            )
            
            lcoe = calculate_lcoe(
                Ef=total_yearly_power,
                T=form_data['years'],
                deg=form_data['degradation_rate'],
                capex=form_data['capex'],
                opex=form_data['opex'],
                Tx=form_data['corp_tax'],
                dr=form_data['discount_rate'],
                inflation=form_data['inflation_rate']
            )
            
            npv_result = calculate_npv(
                capex=form_data['capex'],
                opex=form_data['opex'],
                NPVtotal=0,
                T=form_data['years'],
                Tx=form_data['corp_tax'],
                dr=form_data['discount_rate'],
                day_ahead_avg_price=form_data['day_ahead_avg_price'],
                total_yearly_power=total_yearly_power
            )
            
            # Store results in session
            session['results'] = {
                'yearly_yield': round(total_yearly_power/1000, 2),
                'lcoe': round(lcoe, 4),
                'npv': round(npv_result[0], 2),
                'payback': round(npv_result[7], 1) if npv_result[7] != float('inf') else 'N/A',
                'irr': round(solve_irr(
                    form_data['capex'],
                    npv_result[1],
                    form_data['years']
                )*100, 2)
            }
            session.modified = True
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'redirect': url_for('output'),
                    'economic_data': {
                        'day_ahead_avg_price': form_data['day_ahead_avg_price'],
                        'WACC': form_data['discount_rate'],
                        'CorpTax': form_data['corp_tax'],
                        'capex': form_data['capex'],
                        'opex': form_data['opex']
                    }
                })
            return redirect(url_for('output'))
            
        except Exception as e:
            print(f"Calculation error: {str(e)}")
            session['results'] = {
                'error': f"Calculation error: {str(e)}"
            }
            session.modified = True
            return jsonify({'error': str(e)}), 500
        
    except ValueError as e:
        return jsonify({'error': f'Invalid number format: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500



@app.route('/get_economic_data')
def handle_economic_data_request():
    try:
        longitude = float(request.args.get('longitude'))
        latitude = float(request.args.get('latitude'))
        country = get_country_from_coords(latitude, longitude)
        if country == "Unknown":
            return jsonify({'error': 'Could not determine country from coordinates'}), 400
        
        economic_data = get_economic_data(country)
        if not economic_data:
            return jsonify({'error': 'Economic data not available for this country'}), 404
            
        return jsonify({
            'success': True,
            'country': country,
            'day_ahead_avg_price': economic_data['day_ahead_avg_price'],
            'WACC': economic_data['WACC'],
            'CorpTax': economic_data['CorpTax'],
            'capex': economic_data['capex'],
            'opex': economic_data['opex'],
            'inflation_rate': economic_data['inflation_rate']  # Add this line
        })
    except ValueError:
        return jsonify({'error': 'Invalid longitude/latitude values'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/get_pv_data')
def handle_pv_data_request():
    try:
        longitude = float(request.args.get('longitude'))
        latitude = float(request.args.get('latitude'))
        tilt = float(request.args.get('tilt', 20))
        azimuth = float(request.args.get('azimuth', 180))
        
        pv_data = get_pv_data(longitude=longitude, latitude=latitude, tilt=tilt, azimuth=azimuth)
        return jsonify({
            'success': True,
            'data': pv_data.to_dict()  # Convert DataFrame to dictionary
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calculate_yearly_yield', methods=['POST'])
def handle_yearly_yield_request():
    try:
        # Get form data
        form_data = request.json if request.json else request.form
        
        longitude = float(form_data.get('longitude'))
        latitude = float(form_data.get('latitude'))
        tilt = float(form_data.get('tilt_angle', 10))
        azimuth = float(form_data.get('azimuth', 180))
        dni_extra = float(form_data.get('dni_extra', 1300))
        
        # Get PV data with form tilt and azimuth
        pv_data = get_pv_data(longitude=longitude, latitude=latitude, tilt=tilt, azimuth=azimuth)
        
        # Calculate yield with form parameters
        total_yearly_power = calculate_yearly_yield(
            df=pv_data[0], 
            latitude=latitude, 
            longitude=longitude, 
            dni_extra=dni_extra,
            surface_tilt=tilt,
            surface_azimuth=azimuth
        )
        
        return jsonify({
            'success': True,
            'yearly_yield': total_yearly_power,
            'units': 'kWh/kW',
            'parameters': {
                'tilt': tilt,
                'azimuth': azimuth
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/calculate_lcoe', methods=['POST'])
def handle_lcoe_request():
    try:
        # Get form data
        form_data = request.json if request.json else request.form
        
        longitude = float(form_data.get('longitude'))
        latitude = float(form_data.get('latitude'))
        tilt = float(form_data.get('tilt_angle', 10))
        azimuth = float(form_data.get('azimuth', 180))
        dni_extra = float(form_data.get('dni_extra', 1300))
        years = int(form_data.get('years', 25))
        degradation = float(form_data.get('degradation_rate', 0.01))
        
        # Get country and economic data
        country = get_country_from_coords(latitude, longitude)
        economic_data = get_economic_data(country)
        
        if not economic_data:
            return jsonify({'error': 'Economic data not available for this location'}), 404
        
        # Get PV data with form tilt and azimuth
        pv_data = get_pv_data(longitude=longitude, latitude=latitude, tilt=tilt, azimuth=azimuth)
        
        # Calculate yield with form parameters
        total_yearly_power = calculate_yearly_yield(
            pv_data[0], 
            latitude, 
            longitude, 
            dni_extra,
            surface_tilt=tilt,
            surface_azimuth=azimuth
        )
        
        # Calculate LCOE with form parameters
        lcoe = calculate_lcoe(
            Ef=total_yearly_power,
            T=years,
            deg=degradation,
            Nd=20,
            capex=economic_data['capex'],
            opex=economic_data['opex'],
            Tx=economic_data['CorpTax'],
            dr=economic_data['WACC'],
            inflation=economic_data['inflation_rate']
        )
        
        return jsonify({
            'success': True,
            'lcoe': lcoe,
            'units': 'currency/kWh',
            'parameters': {
                'tilt': tilt,
                'azimuth': azimuth
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/calculate_npv', methods=['POST'])
def handle_npv_request():
    try:
        # Get form data
        form_data = request.json if request.json else request.form
        
        longitude = float(form_data.get('longitude'))
        latitude = float(form_data.get('latitude'))
        tilt = float(form_data.get('tilt_angle', 10))
        azimuth = float(form_data.get('azimuth', 180))
        dni_extra = float(form_data.get('dni_extra', 1300))
        years = int(form_data.get('years', 25))
        
        # Get country and economic data
        country = get_country_from_coords(latitude, longitude)
        economic_data = get_economic_data(country)
        
        if not economic_data:
            return jsonify({'error': 'Economic data not available for this location'}), 404
        
        # Get PV data with form tilt and azimuth
        pv_data = get_pv_data(longitude=longitude, latitude=latitude, tilt=tilt, azimuth=azimuth)
        
        # Calculate yield with form parameters
        total_yearly_power = calculate_yearly_yield(
            pv_data[0], 
            latitude, 
            longitude, 
            dni_extra,
            surface_tilt=tilt,
            surface_azimuth=azimuth
        )
        
        # Calculate NPV with form parameters
        npv_result = calculate_npv(
            capex=economic_data['capex'],
            opex=economic_data['opex'],
            NPVtotal=0,
            T=years,
            Tx=economic_data['CorpTax'],
            dr=economic_data['WACC'],
            day_ahead_avg_price=economic_data['day_ahead_avg_price'],
            total_yearly_power=total_yearly_power
        )
        
        return jsonify({
            'success': True,
            'npv': npv_result[0],
            'revenue': npv_result[1],
            'payback': npv_result[7],
            'units': 'currency',
            'parameters': {
                'tilt': tilt,
                'azimuth': azimuth
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/calculate_irr')
def handle_irr_request():
    try:
        capex = float(request.args.get('capex'))
        cashflow = float(request.args.get('cashflow'))
        years = int(request.args.get('years', 25))
        
        irr = solve_irr(capex, cashflow, years)
        
        return jsonify({
            'success': True,
            'irr': irr,
            'units': 'decimal'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/calculate_dcf')
def handle_dcf_request():
    try:
        capex = float(request.args.get('capex'))
        cashflow = float(request.args.get('cashflow'))
        dr = float(request.args.get('discount_rate'))
        
        dcf = calculate_dcf(capex, cashflow, dr)
        
        return jsonify({
            'success': True,
            'dcf': dcf,
            'units': 'years'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_country_from_coords(lat, lon, max_retries=3):
    geolocator = Nominatim(user_agent="geo_location")
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

def get_economic_data(country_name, file_path=None):
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
                'day_ahead_avg_price': float(country_data['DayAVG'].values[0]),
                'inflation_rate': float(country_data['Inflation'].values[0]),
                'capex': float(country_data['capex'].values[0]),
                'opex': float(country_data['opex'].values[0]),
                'WACC': float(country_data['WACC'].values[0]),
                'CorpTax': float(country_data['CorpTax'].values[0])
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

def get_pv_data(longitude, latitude, tilt, azimuth, start=2020, end=2020):
    try:
        # Use the correct parameter names for PVGIS
        pv_data = pvlib.iotools.get_pvgis_hourly(
            latitude=latitude,
            longitude=longitude,
            surface_tilt=tilt,  # Changed from 'tilt' to 'surface_tilt'
            surface_azimuth=azimuth,  # Changed from 'azimuth' to 'surface_azimuth'
            start=start,
            end=end,
            raddatabase="PVGIS-SARAH3",
            components=True,
            outputformat='json',
            usehorizon=True,
            pvtechchoice='crystSi',
            mountingplace='free',
            loss=0
        )
        return pv_data
    except Exception as e:
        print(f"Error in get_pv_data: {str(e)}")
        raise e

def calculate_yearly_yield(df, latitude, longitude, dni_extra, surface_tilt=20, u_c=56, u_v=0, 
                         albedo=0.06, surface_azimuth=180., gamma_pdc=-0.0034, pdc0=1., 
                         p_losses=0.14, inv_eff=0.96, module_efficiency=0.1, alpha_absorption=0.9):
    total_power = 0
    for t in range(1, 8760, 1):
        try:
            DNI = df.iloc[t, 0]
            BNI = df.iloc[t, 1]
            zenith = 90 - df.iloc[t, 3]
            azimuth = 0
            temp_air = df.iloc[t, 4]
            wind_speed = df.iloc[t, 5]
            
            GHI = BNI + DNI
            airmass_relative = pvlib.atmosphere.get_relative_airmass(zenith, model='kastenyoung1989')
            airmass = pvlib.atmosphere.get_absolute_airmass(airmass_relative)
            aoi = pvlib.irradiance.aoi(surface_tilt, surface_azimuth, zenith, azimuth)
            iam = pvlib.iam.physical(aoi)
            
            poa_ground_diffuse = pvlib.irradiance.get_ground_diffuse(surface_tilt, GHI, albedo)
            poa_sky_diffuse = pvlib.irradiance.get_sky_diffuse(
                surface_tilt, surface_azimuth, zenith, azimuth, 
                BNI, GHI, DNI, dni_extra, airmass=airmass, 
                model='isotropic')
            poa = pvlib.irradiance.poa_components(aoi, BNI, poa_sky_diffuse, poa_ground_diffuse)
            
            temp_cell = pvlib.temperature.pvsyst_cell(
                poa['poa_global'], temp_air, wind_speed, u_c, u_v, 
                module_efficiency, alpha_absorption=alpha_absorption)
            
            g_poa_effective = poa['poa_direct'] * iam + poa['poa_diffuse']
            pv_yield = pvlib.pvsystem.pvwatts_dc(g_poa_effective, temp_cell, pdc0, gamma_pdc, temp_ref=25.0)
            
            total_power += pv_yield * inv_eff * (1 - p_losses)
            
        except Exception:
            continue
    
    return total_power

def calculate_lcoe(Ef, T=25, deg=0.01, Nd=20, capex=1200, opex=20, Tx=20, dr=6.5, inflation=2.5):
    Dn = capex / Nd
    lcoe_num = capex
    lcoe_den = 0
    
    for year in np.arange(1, T + 1):
        lcoe_num += opex * (1 - Tx / 100) * (1 + inflation / 100) ** year / (1 + dr / 100) ** year
        if year <= Nd:
            lcoe_num -= (Dn * Tx / 100) / (1 + dr / 100) ** year
        lcoe_den += (Ef * (1 - deg) ** year) / (1 + dr / 100) ** year
    
    return lcoe_num / lcoe_den

def calculate_npv(capex, opex, NPVtotal, T, Tx, dr, day_ahead_avg_price, total_yearly_power):
    for year in range(1, T + 1):
        revenue = day_ahead_avg_price * total_yearly_power / 1000
        discountedCF = (revenue * (1 - Tx / 100) - opex) / (1 + dr / 100) ** year
        NPVtotal += discountedCF
    
    NPV2 = (revenue * (1 - Tx / 100) - opex) / (1 + dr / 100) ** T
    payback = capex / (revenue * (1 - Tx / 100) - opex) if (revenue * (1 - Tx / 100) - opex) > 0 else float('inf')
    
    return NPVtotal-capex, revenue, capex, opex, Tx, dr, NPV2, payback

def solve_irr(capex, cashflow, years, tol=1e-6, max_iter=50):
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

def calculate_dcf(capex, cashflow, dr):
    cumulative_pv = 0.0
    year = 0
    
    while cumulative_pv < capex:
        year += 1
        pv = cashflow / ((1 + dr / 100) ** year)
        cumulative_pv += pv

        if cumulative_pv >= capex:
            cumulative_pv -= pv
            remaining = capex - cumulative_pv
            fraction = remaining / pv
            return year - 1 + fraction

        if year > 1000:
            return None
    return year

@app.route('/output')
def output():
    form_data = session.get('form_data', {})
    results = session.get('results', {})
    
    if 'error' in results:
        return render_template('output2.html', 
            error=results['error'],
            location="Error",
            coordinates="N/A",
            system_size="N/A",
            tilt_angle="N/A",
            azimuth="N/A",
            map_lat=0,
            map_lng=0
        )
    
    try:
        floating_lcoe = results.get('lcoe', 0)
        ground_lcoe = round(floating_lcoe * 0.9, 4) if floating_lcoe and floating_lcoe != 0 else 0
        rooftop_lcoe = round(floating_lcoe * 1.1, 4) if floating_lcoe and floating_lcoe != 0 else 0
        wind_lcoe = round(floating_lcoe * 1.3, 4) if floating_lcoe and floating_lcoe != 0 else 0
        
        regional_avg = round(results.get('yearly_yield', 0) * 0.9, 2) if results.get('yearly_yield') else 0
        yield_difference = round((results.get('yearly_yield', 0) - regional_avg)/regional_avg * 100, 1) if regional_avg != 0 else 0
    except Exception:
        ground_lcoe = rooftop_lcoe = wind_lcoe = regional_avg = yield_difference = 0
    
    return render_template('output2.html',
        location=form_data.get('country', 'Unknown'),
        coordinates=f"{form_data.get('latitude', 0)}, {form_data.get('longitude', 0)}",
        system_size=form_data.get('system_size', 0),
        tilt_angle=form_data.get('tilt_angle', 10),
        azimuth=form_data.get('azimuth', 180),
        map_lat=form_data.get('latitude', 0),
        map_lng=form_data.get('longitude', 0),
        yearly_yield=results.get('yearly_yield', 'Calculating...'),
        irradiance="Calculating...",
        performance_ratio="Calculating...",
        your_yield=results.get('yearly_yield', 'Calculating...'),
        regional_avg=regional_avg,
        yield_difference=yield_difference,
        lcoe=results.get('lcoe', 'Calculating...'),
        npv=results.get('npv', 'Calculating...'),
        payback=results.get('payback', 'Calculating...'),
        irr=results.get('irr', 'Calculating...'),
        floating_lcoe=results.get('lcoe', 'Calculating...'),
        ground_lcoe=ground_lcoe,
        rooftop_lcoe=rooftop_lcoe,
        wind_lcoe=wind_lcoe,
        day_ahead_avg_price=form_data.get('day_ahead_avg_price', 0.15),
        discount_rate=form_data.get('discount_rate', 6.5),
        corp_tax=form_data.get('corp_tax', 20)
    )

if __name__ == '__main__':
    app.run(debug=True)