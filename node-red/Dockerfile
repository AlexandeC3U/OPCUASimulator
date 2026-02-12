FROM nodered/node-red:latest

# Install additional palette nodes into the Node-RED installation directory
# (not /data, which will be bind-mounted)
WORKDIR /usr/src/node-red
RUN npm install --unsafe-perm --no-audit --no-fund \
    node-red-contrib-influxdb@~0.7.0 \
    node-red-contrib-opcua@0.2.348