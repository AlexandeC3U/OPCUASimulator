# SORT3 PLC Simulator

A complete simulation environment for the SORT3 workcenter PLC, including OPC UA server, MQTT integration, and Grafana visualization.

## Architecture

```
┌─────────────┐     MQTT Commands      ┌───────────────────┐
│   Client    │ ─────────────────────> │      EMQX         │
│  (MQTT)     │ <───────────────────── │   MQTT Broker     │
└─────────────┘     MQTT Status        └─────────┬─────────┘
                                                 │
                                                 ▼
                                       ┌───────────────────┐
                                       │  OPC UA Simulator │
                                       │   (Python)        │
                                       │                   │
                                       │  - All SORT3 Tags │
                                       │  - Simulation     │
                                       └─────────┬─────────┘
                                                 │
                                                 │ OPC UA
                                                 ▼
                                       ┌───────────────────┐
                                       │     Telegraf      │
                                       │  (Data Collector) │
                                       └─────────┬─────────┘
                                                 │
                                                 ▼
                                       ┌───────────────────┐
                                       │     InfluxDB      │
                                       │  (Time Series DB) │
                                       └─────────┬─────────┘
                                                 │
                                                 ▼
                                       ┌───────────────────┐
                                       │     Grafana       │
                                       │  (Visualization)  │
                                       └───────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Ports available: 1883 (MQTT), 4840 (OPC UA), 8086 (InfluxDB), 3000 (Grafana), 18083 (EMQX Dashboard)

### Start the Simulation

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| EMQX Dashboard | http://localhost:18083 | admin / public |
| InfluxDB | http://localhost:8086 | admin / adminpassword123 |
| OPC UA Server | opc.tcp://localhost:4840/freeopcua/server/ | - |
| MQTT Broker | localhost:1883 | - |

## MQTT Topics

### Command Topics (Subscribe by Simulator)

| Topic | Description | Payload Example |
|-------|-------------|-----------------|
| `menen/sort3/start_order` | Start a production order | See below |
| `menen/sort3/stop_order` | Stop current order | `{}` |
| `menen/sort3/config` | Update configuration | `{"belt_speed": 120}` |
| `menen/sort3/simulate/veneer_stacked` | Manually trigger veneer stacked | `{"qty_increment": 1}` |
| `menen/sort3/set_tag/<tag_name>` | Set individual tag value | Value |

### Status Topics (Published by Simulator)

| Topic | Description |
|-------|-------------|
| `menen/sort3/status/simulator_started` | Simulator has started |
| `menen/sort3/status/simulator_stopped` | Simulator has stopped |
| `menen/sort3/status/order_started` | Production order started |
| `menen/sort3/status/order_stopped` | Production order stopped |
| `menen/sort3/status/veneer_stacked` | Veneer was stacked (with details) |
| `menen/sort3/status/config_updated` | Configuration was updated |

## Example MQTT Commands

### Start a Production Order

```json
{
  "po_id": "PO-2024-001",
  "belt_speed": 100.0,
  "max_sheets": 50,
  "open_distance": 10.0,
  "stations": [
    {
      "active": true,
      "cutting": false,
      "itemname": "VENEER-OAK-2400",
      "tape": true,
      "veneer_l": 2400.0
    },
    {
      "active": true,
      "cutting": true,
      "itemname": "VENEER-WALNUT-1800",
      "tape": false,
      "veneer_l": 1800.0
    }
  ]
}
```

### Using mosquitto_pub (install mosquitto-clients)

```bash
# Start an order
mosquitto_pub -h localhost -t "menen/sort3/start_order" -m '{
   "po_id":"PO-2024-001",
   "po_qty":100,
   "belt_speed":100.0,
   "max_sheets":50,
   "open_distance":10.0,
   "speedbelt":20.0,
   "stations":[
      {
         "active":true,
         "cutting":false,
         "box1_material":"VENEER-OAK-2400",
         "tape":true,
         "veneer_l":2400.0
      },
      {
         "active":true,
         "cutting":false,
         "box2_material":"VENEER-WALNUT-1800",
         "tape":false,
         "veneer_l":1800.0
      },      
      {
         "active":true,
         "cutting":false,
         "box3_material":"MacAndCheese",
         "tape":false,
         "veneer_l":500.0
      }
   ]
}'

# Stop an order
mosquitto_pub -h localhost -t "menen/sort3/stop_order" -m '{}'

# Manually trigger veneer stacked
mosquitto_pub -h localhost -t "menen/sort3/simulate/veneer_stacked" -m '{"qty_increment":5}'

# Set individual tag
mosquitto_pub -h localhost -t "menen/sort3/set_tag/BB_CUTTING" -m 'true'
```

## OPC UA Tag Structure

```
OBJT_SORT3
└── SORT3
    ├── STARTED_PO
    │   ├── SRT_OBJT_NEW_VALUE (boolean)
    │   ├── SRT_PLC_VALUE_PROCESSED (boolean)
    │   ├── SRT_PO_ID (string)
    │   ├── SRT_PO_QTY (boolean)
    │   ├── SRT3_IN2 (string)
    │   ├── SRT_SPEEDBELTTRANSPORT (numeric)
    │   ├── SRT_MAXSHEETSBOX (numeric)
    │   ├── SRT_OPENBOXDISTNACE (numeric)
    │   ├── SRT_1_ACTIVE ... SRT_6_ACTIVE (boolean)
    │   ├── SRT_1_CUTTING ... SRT_6_CUTTING (boolean)
    │   ├── SRT_1_ITEMNAME ... SRT_6_ITEMNAME (string)
    │   ├── SRT_1_TAPE ... SRT_6_TAPE (boolean)
    │   └── SRT_1_VENEER_L ... SRT_6_VENEER_L (numeric)
    │
    ├── BLOCK_OUTPUT
    │   ├── BB_BOX_BLOCK (boolean)
    │   ├── BB_CUTTING (boolean)
    │   ├── BB_ITEMNAME (string)
    │   ├── BB_OBJT_NEW_VALUE (boolean)
    │   ├── BB_OUT_BOXNR (numeric)
    │   ├── BB_PLC_VALUE_PROCESSED (boolean)
    │   ├── BB_TAPE (boolean)
    │   └── BB_VENEER_L (numeric)
    │
    └── VENEER_STACKED
        ├── OUT_BOXFULL (boolean)
        ├── OUT_BOXNR (numeric)
        ├── OUT_LPN_ID (string)
        ├── OUT_LPN_QTY (numeric)
        ├── OUT_OBJT_VALUE_PROCESSED (boolean)
        ├── OUT_PLC_NEW_VALUE (boolean)
        ├── OUT_REPAIR (boolean)
        └── OUT_PO_ID (string)
```

## Simulation Behavior

When an order is started via MQTT:

1. **Order Initialization**
   - Sets `SRT_PO_ID`, `SRT_OBJT_NEW_VALUE = true`
   - Fills custom attributes (belt speed, max sheets, open distance)
   - Configures sort stations from payload

2. **Veneer Stacking Simulation**
   - Every `SIMULATION_INTERVAL` seconds (default: 5s), a veneer is "stacked"
   - `OUT_LPN_QTY` increments by 1
   - `OUT_PLC_NEW_VALUE` pulses to true
   - When `OUT_LPN_QTY >= SRT_MAXSHEETSBOX`, box is marked full
   - Box number increments and quantity resets

3. **Status Publishing**
   - Events are published to MQTT for monitoring
   - All tag values are collected by Telegraf and stored in InfluxDB

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | `emqx` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `OPCUA_PORT` | `4840` | OPC UA server port |
| `SIMULATION_INTERVAL` | `5` | Seconds between veneer stack events |

## Grafana Dashboard

The pre-configured dashboard shows:

- **Veneer Stacked Section**: Current LPN quantity, box number, box full status, repair status, PLC new value indicator
- **Production Order Section**: Order ID, active status, belt speed, max sheets, open distance
- **Sort Stations**: Status of all 6 sort stations
- **Block Output**: Block box status, veneer length, blocked/cutting/tape status
- **Time Series Charts**: LPN quantity and box number over time

## Troubleshooting

### OPC UA Connection Issues

```bash
# Check if OPC UA simulator is running
docker-compose logs opcua-simulator

# Test OPC UA connection (using Python)
pip install asyncua
python -c "
import asyncio
from asyncua import Client

async def test():
    client = Client('opc.tcp://localhost:4840/freeopcua/server/')
    await client.connect()
    print('Connected!')
    await client.disconnect()

asyncio.run(test())
"
```

### MQTT Connection Issues

```bash
# Check EMQX status
docker-compose logs emqx

# Subscribe to all SORT3 topics
mosquitto_sub -h localhost -t "menen/sort3/#" -v
```

### Telegraf/InfluxDB Issues

```bash
# Check Telegraf logs
docker-compose logs telegraf

# Check InfluxDB
docker-compose logs influxdb
```

## Development

### Modifying the Simulator

The simulator code is in `opcua-simulator/main.py`. After making changes:

```bash
docker-compose build opcua-simulator
docker-compose up -d opcua-simulator
```

### Adding New Tags

1. Add the tag to `self.state` dictionary in `Sort3Simulator.__init__`
2. Create the OPC UA node in the appropriate `_create_*_nodes` method
3. Add the node to `telegraf/telegraf.conf` for data collection
4. Update the Grafana dashboard if needed

## License

Internal use only - Decospan
