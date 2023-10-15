FROM python:3.11

# Expose port 7001 for the Flask app to listen on
EXPOSE 7001

# Use ARG for build-time variables
ARG DB_USERNAME
ARG DB_PASSWORD
ARG DB_HOST
ARG DB_PORT
ARG USE_SRV

# Set them as environment variables so the application can use them
ENV DB_USERNAME=$DB_USERNAME
ENV DB_PASSWORD=$DB_PASSWORD
ENV DB_HOST=$DB_HOST
ENV DB_PORT=$DB_PORT
ENV USE_SRV=$USE_SRV

ADD requirements.txt .
ADD analysis.py .
ADD dsm_local_array.npy .
ADD shadowingfunction_wallheight_13.py .
ADD solarposition.py .

# Install the required Python libraries
RUN pip3 install --no-cache-dir -r requirements.txt

# Define an entry point script to:
# - Run the application
RUN echo "#!/bin/bash" > /root/entrypoint.sh && \
    echo "python3 analysis.py" >> /root/entrypoint.sh && \
    chmod +x /root/entrypoint.sh

ENTRYPOINT ["/root/entrypoint.sh"]
