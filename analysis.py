import base64
import datetime
import gzip
import logging
import os
import pickle
from datetime import datetime
from io import BytesIO

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from flask import Flask
from flask import jsonify
from flask_cors import CORS
from pymongo import MongoClient

import shadowingfunction_wallheight_13 as shadow
import solarposition as solarposition

app = Flask(__name__)
CORS(app)
mpl.use('Agg')


def calculate_shadow_matrix(timestamp):
    """
    Calculate the shadow matrix based on the sun's azimuth and elevation.
    """
    df_solar = solarposition.get_solarposition(timestamp, latitude, longitude)

    altitude = df_solar['elevation'][0]
    azimuth = df_solar['azimuth'][0]

    scale = 1
    walls = np.zeros((dsm.shape[0], dsm.shape[1]))
    dirwalls = np.zeros((dsm.shape[0], dsm.shape[1]))

    shadow_matrix, _, _, _, _ = shadow.shadowingfunction_wallheight_13(dsm, azimuth, altitude, scale,
                                                                       walls,
                                                                       dirwalls * np.pi / 180.)
    return shadow_matrix


def save_shadow_matrix(data):
    """Insert shadow matrix into MongoDB."""
    logging.info("Saving shadow matrix to database.")
    collection = db['shadow_matrices']
    collection.insert_one(data)


def generate_heatmap(matrix):
    plt.figure(figsize=(10, 8))
    sns.heatmap(matrix, cmap='viridis')

    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)

    # Encode the PNG image to base64
    base64_encoded_image = base64.b64encode(buf.getvalue()).decode('utf-8')

    return base64_encoded_image


def generate_surface_plot(shadow_matrix):
    # Generate x and y coordinates
    x = np.linspace(0, shadow_matrix.shape[1] - 1, shadow_matrix.shape[1])
    y = np.linspace(0, shadow_matrix.shape[0] - 1, shadow_matrix.shape[0])
    X, Y = np.meshgrid(x, y)

    # Normalize the dsm array to be between 0 and 1 for RGB representation
    dsm_normalized = (dsm - np.min(dsm)) / (np.max(dsm) - np.min(dsm))
    img = plt.cm.viridis(dsm_normalized)[:, :, :3]

    # Create the surface plot
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_surface(X, Y, shadow_matrix, facecolors=img, shade=False)

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Shadow Value')

    # Convert the plot to a PNG image
    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    # Encode the PNG image to base64
    base64_encoded_image = base64.b64encode(buf.getvalue()).decode('utf-8')

    return base64_encoded_image


def compress_data(data):
    compressed_data = gzip.compress(pickle.dumps(data))
    return compressed_data


@app.route('/calculate-shadow', methods=['GET'])
def calculate_shadow():
    timestamp = datetime.now()
    shadow_matrix = calculate_shadow_matrix(timestamp)

    try:
        save_shadow_matrix({'timestamp': timestamp, 'shadow_matrix': compress_data(shadow_matrix)})
        logging.info("Shadow matrix saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save shadow matrix to database. Error: {str(e)}")

    heatmap = generate_heatmap(shadow_matrix)
    surface_plot = generate_surface_plot(shadow_matrix)

    formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')

    response = jsonify({
        "timestamp": formatted_time,
        "heatmap": heatmap,
        "surface_plot": surface_plot
    })
    response.headers['Content-Type'] = 'application/json'
    return response


if __name__ == '__main__':
    # Set up logging configuration
    logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

    db_username = os.environ.get('DB_USERNAME')
    db_password = os.environ.get('DB_PASSWORD')
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    use_srv = os.environ.get('USE_SRV')
    use_srv = True if use_srv == "True" else False

    # Initialize the MongoDB client
    if not use_srv:
        client = MongoClient(db_host, db_port)
    else:
        connection_str = f"mongodb+srv://{db_username}:{db_password}@{db_host}/?retryWrites=true&w=majority"
        client = MongoClient(connection_str)
    db = client.get_database(name='shadow_matrix')

    # Read hard coded model data
    latitude = 29.73463
    longitude = -95.30052
    dsm = np.load('./dsm_local_array.npy')
    dsm = np.nan_to_num(dsm, nan=0)

    app.run(host='0.0.0.0', port=7001)
