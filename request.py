from flask import Flask, request, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html',methods=["GET", "POST"])  # Make sure to put the HTML in a templates folder

@app.route('/submit', methods=['POST'])
def handle_submission():
    # System Parameters
    location_method = request.form.get('location_method')
    system_size = request.form.get('system-size')
    tilt_angle = request.form.get('tilt-angle')
    years = request.form.get('years')
    system_loss = request.form.get('system-loss')
    panel_efficiency = request.form.get('panel-efficiency')
    degradation_rate = request.form.get('degradation-rate')
    azimuth = request.form.get('azimuth')
    uv = request.form.get('Uv')
    uc = request.form.get('Uc')
    
    # Location data
    if location_method == 'coordinates-btn':
        longitude = request.form.get('longitude')
        latitude = request.form.get('latitude')
        country = None
    else:
        country = request.form.get('Country1')
        longitude = None
        latitude = None
    
    # Economic Parameters
    capex = request.form.get('capex')
    opex = request.form.get('opex')
    discount_rate = request.form.get('discount-rate')
    inflation_rate = request.form.get('inflation-rate')
    
    # File uploads
    irradiance_file = request.files.get('irradiance-data')
    economic_file = request.files.get('economic-data')
    
    # Save uploaded files if they exist
    if irradiance_file and irradiance_file.filename:
        irradiance_path = os.path.join('uploads', irradiance_file.filename)
        irradiance_file.save(irradiance_path)
    
    if economic_file and economic_file.filename:
        economic_path = os.path.join('uploads', economic_file.filename)
        economic_file.save(economic_path)
    
    # Prepare response data (in a real app, you'd process this data)
    response_data = {
        'system_parameters': {
            'location_method': location_method,
            'longitude': longitude,
            'latitude': latitude,
            'country': country,
            'system_size_kw': system_size,
            'tilt_angle': tilt_angle,
            'years': years,
            'system_loss': system_loss,
            'panel_efficiency': panel_efficiency,
            'degradation_rate': degradation_rate,
            'azimuth': azimuth,
            'Uv': uv,
            'Uc': uc
        },
        'economic_parameters': {
            'capex': capex,
            'opex': opex,
            'discount_rate': discount_rate,
            'inflation_rate': inflation_rate
        },
        'files': {
            'irradiance_file': irradiance_file.filename if irradiance_file else None,
            'economic_file': economic_file.filename if economic_file else None
        }
    }
    
    return response_data
print(handle_submission())
if __name__ == '__main__':
    # Create uploads directory if it doesn't exist
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    
    app.run(debug=True, host='0.0.0.0')