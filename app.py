from flask import Flask, render_template, request
import math
import datetime

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        try:
            # Get inputs from the form
            date = datetime.datetime.today().strftime('%d-%b-%Y')
            callsign = request.form.get('callsign', 'N/A')
            frequency = float(request.form.get('frequency'))
            units = request.form.get('units')
            specify = request.form.get('specify')
            gain = None
            boom_length = None
            if specify == 'gain':
                gain = float(request.form.get('gain'))
            else:
                boom_length = float(request.form.get('boom_length'))
            element_mounting = request.form.get('element_mounting')
            boom_diameter = None
            if element_mounting != '3':
                boom_diameter = float(request.form.get('boom_diameter'))
            driven_element_diameter = float(request.form.get('driven_element_diameter'))
            parasitic_element_diameter = float(request.form.get('parasitic_element_diameter'))
        except (ValueError, TypeError):
            error = 'Invalid input. Please check your inputs.'
            return render_template('index.html', error=error)

        # Perform calculations
        try:
            results = calculate_yagi(
                frequency,
                units,
                specify,
                gain,
                boom_length,
                element_mounting,
                boom_diameter,
                driven_element_diameter,
                parasitic_element_diameter
            )
        except Exception as e:
            error = str(e)
            return render_template('index.html', error=error)

        return render_template('results.html', results=results, date=date, callsign=callsign)
    else:
        return render_template('index.html', error=error)

def calculate_yagi(frequency, units, specify, gain, boom_length, element_mounting, boom_diameter,
                   driven_element_diameter, parasitic_element_diameter):

    # Constants
    MM_PER_INCH = 25.4
    C = 299792.458  # Speed of light in km/s

    # Wavelength in mm
    #wavelength_mm = (299792.458 / frequency) * 1000  # Incorrect: Multiplying by 1000 causes error
    wavelength_mm = 299792.458 / frequency  # Correct: This gives the wavelength in mm


    # Convert units to wavelengths
    if units == '1':  # inches
        unit_factor = MM_PER_INCH / wavelength_mm
    elif units == '2':  # millimeters
        unit_factor = 1 / wavelength_mm
    elif units == '3':  # wavelengths
        unit_factor = 1
    else:
        raise ValueError('Invalid unit selection')

    # Calculate boom length and gain
    if specify == 'gain':
        if gain < 11.8 or gain > 21.6:
            raise ValueError('Gain must be between 11.8 dBd and 21.6 dBd')
        # Estimate boom length
        BL = math.exp((gain - 9.2) / 3.39)
    else:
        # boom_length is given in selected units, convert to wavelengths
        BL = boom_length * unit_factor
        if BL < 2.2 or BL > 39:
            raise ValueError('Boom length must be between 2.2 and 39 wavelengths')
        # Estimate gain
        gain = 9.2 + 3.39 * math.log(BL)

    # Element mounting options
    if element_mounting == '3':
        BC = 0  # No boom correction
    else:
        # Convert boom diameter to wavelengths
        BD = boom_diameter * unit_factor
        if BD > 0.06:
            raise ValueError('Boom diameter must be less than 0.06 wavelengths')

        # Calculate boom correction factor
        BC1 = 733 * BD * (0.055 - BD) - 504 * BD * (0.03 - BD)
        if element_mounting == '2':
            BC1 /= 2  # Insulated elements
        BC = BC1 * BD  # Boom correction

    # Convert element diameters to wavelengths
    DD = driven_element_diameter * unit_factor
    ED = parasitic_element_diameter * unit_factor
    if not (0.001 <= DD <= 0.02):
        raise ValueError('Driven element diameter must be between 0.001 and 0.02 wavelengths')
    if not (0.001 <= ED <= 0.02):
        raise ValueError('Parasitic element diameter must be between 0.001 and 0.02 wavelengths')

    # Calculate element spacings and lengths
    S, T, M, LL, G1 = calculate_elements(BL)
    D = calculate_director_lengths(M, ED, BC)

    # Calculate reflector length
    XR = 20  # Reflector reactance recommended by DL6WU
    R = (((XR - 40) / (186.8769 * math.log(2 / ED) - 320)) + 1) / 2
    R += BC

    # Calculate driven element length
    DE = (.4777 - (1.0522 * DD) + (.43363 * (DD ** -0.014891))) / 2
    DE *= 1.02  # Modified by DL6WU
    DE += BC

    # Convert lengths to desired units
    unit_conversion = {
        '1': wavelength_mm / MM_PER_INCH,  # wavelengths to inches
        '2': wavelength_mm,                # wavelengths to mm
        '3': 1                             # wavelengths to wavelengths
    }
    length_unit = 'inches' if units == '1' else 'mm' if units == '2' else 'wavelengths'

    # Prepare results
    results = {
        'frequency': frequency,
        'gain': round(G1, 2),
        'boom_length': round(LL * unit_conversion[units], 2),
        'boom_length_unit': length_unit,
        'number_of_elements': M + 2,  # Including reflector and driven element
        'elements': []
    }

    # Add reflector
    results['elements'].append({
        'position': 0,
        'type': 'Reflector',
        'length': round(R * unit_conversion[units], 4)
    })

    # Add driven element
    results['elements'].append({
        'position': round(0.2 * unit_conversion[units], 4),
        'type': 'Driven Element',
        'length': round(DE * unit_conversion[units], 4)
    })

    # Add directors
    for i in range(M):
        results['elements'].append({
            'position': round(T[i] * unit_conversion[units], 4),
            'type': f'Director {i + 1}',
            'length': round(D[i] * unit_conversion[units], 4)
        })

    return results

def calculate_elements(BL):
    SR = 0.2  # Reflector spacing in wavelengths
    S = []  # Spacings between directors
    T = []  # Cumulative spacings from the reflector
    LA = BL  # Available boom length

    S_data = [0.075, 0.180, 0.215, 0.250, 0.280, 0.300, 0.315,
              0.330, 0.345, 0.360, 0.375, 0.390, 0.400, 0.400]

    LA -= SR  # Subtract reflector spacing
    N = 1
    while True:
        if N <= 14:
            spacing = S_data[N - 1]
        else:
            spacing = S_data[-1]  # Use last spacing value for N >= 15

        LA -= spacing  # Decrement available boom length
        if LA < 0:
            M = N - 1  # Found last director
            break

        S.append(spacing)
        if N == 1:
            T.append(SR + spacing)
        else:
            T.append(T[-1] + spacing)
        N += 1

    LL = T[-1] if T else 0  # Actual boom length used

    # Re-estimate gain from actual boom length
    if LL > 0:
        G1 = 9.2 + 3.39 * math.log(LL)
    else:
        G1 = 0

    return S, T, M, LL, G1

def calculate_director_lengths(M, ED, BC):
    element_data = [
        (0.001, 0.4711, 0.018, 0.08398, 0.965),
        (0.003, 0.462, 0.01941, 0.08543, 0.9697),
        (0.005, 0.4538, 0.02117, 0.0951, 1.007),
        (0.007, 0.4491, 0.02274, 0.08801, 0.9004),
        (0.01, 0.4421, 0.02396, 0.1027, 1.038),
        (0.015, 0.4358, 0.02558, 0.1149, 1.034),
        (0.02, 0.4268, 0.02614, 0.1112, 1.036)
    ]

    # Find lower and upper data for interpolation
    lower_data = None
    upper_data = None
    for data in element_data:
        K = data[0]
        if K == ED:
            J = 0
            K1, K2, K3, K4 = data[1:]
            break
        elif K < ED:
            lower_data = data
        elif K > ED and not upper_data:
            upper_data = data
            break
    else:
        # Use closest data if out of range
        if ED <= element_data[0][0]:
            K1, K2, K3, K4 = element_data[0][1:]
            J = 0
        else:
            K1, K2, K3, K4 = element_data[-1][1:]
            J = 0

    if 'J' not in locals():
        # Interpolation
        L = lower_data[0]
        H = upper_data[0]
        J = (ED - L) / (H - L)
        KL1, KL2, KL3, KL4 = lower_data[1:]
        KH1, KH2, KH3, KH4 = upper_data[1:]

    D = []
    for N in range(1, M + 1):
        if J == 0:
            length = (K1 - K2 * math.log(N)) * (1 - K3 * math.exp(-K4 * N))
        else:
            DL_N = (KL1 - KL2 * math.log(N)) * (1 - KL3 * math.exp(-KL4 * N))
            DH_N = (KH1 - KH2 * math.log(N)) * (1 - KH3 * math.exp(-KH4 * N))
            length = DL_N + J * (DH_N - DL_N)
        length += BC  # Apply boom correction
        D.append(length)
    return D

if __name__ == '__main__':
    app.run(debug=True)
