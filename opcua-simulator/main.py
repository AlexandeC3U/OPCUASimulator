"""
SORT3 OPC UA Simulator with MQTT Integration

Simple simulator that:
- Listens for start_order -> starts simulating OPC UA data
- Listens for stop_order -> stops simulation
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from asyncua import Server, ua
from asyncua.common.node import Node

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Sort3Simulator")

# Environment variables
MQTT_BROKER = os.getenv("MQTT_BROKER", "emqx")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
OPCUA_PORT = int(os.getenv("OPCUA_PORT", "4840"))
SIMULATION_INTERVAL = int(os.getenv("SIMULATION_INTERVAL", "5"))


class Sort3Simulator:
    """SORT3 PLC Simulator with OPC UA server and MQTT integration."""

    def __init__(self):
        self.server: Optional[Server] = None
        self.running = False
        self.order_active = False
        self.current_order = ""
        
        # OPC UA node references
        self.nodes: Dict[str, Node] = {}
        
        # Track quantities for each of the 6 boxes
        self.box_quantities = {i: 0 for i in range(1, 7)}
        
        # Current state
        self.state = {
            # STARTED_PO
            "SRT_OBJT_NEW_VALUE": False,
            "SRT_PLC_VALUE_PROCESSED": False,
            "SRT_PO_ID": "",
            "SRT_PO_QTY": 0,
            "SRT3_IN2": "",
            "ORDER_STATUS": 0,  # 1=active, 0=stopped
            
            # CUSTOM_ATTRIBUTES
            "SRT_SPEEDBELTTRANSPORT": 0.0,
            "SRT_MAXSHEETSBOX": 0.0,
            "SRT_OPENBOXDISTNACE": 0.0,
            
            # SORT stations 1-6
            **{f"SRT_{i}_ACTIVE": False for i in range(1, 7)},
            **{f"SRT_{i}_CUTTING": False for i in range(1, 7)},
            **{f"SRT_{i}_ITEMNAME": "" for i in range(1, 7)},
            **{f"SRT_{i}_TAPE": False for i in range(1, 7)},
            **{f"SRT_{i}_VENEER_L": 0.0 for i in range(1, 7)},
            **{f"SRT_{i}_QTY": 0 for i in range(1, 7)},
            
            # BLOCK_OUTPUT
            "BB_BOX_BLOCK": False,
            "BB_CUTTING": False,
            "BB_ITEMNAME": "",
            "BB_OBJT_NEW_VALUE": False,
            "BB_OUT_BOXNR": 0,
            "BB_PLC_VALUE_PROCESSED": False,
            "BB_TAPE": False,
            "BB_VENEER_L": 0.0,
            
            # VENEER_STACKED
            "OUT_BOXFULL": False,
            "OUT_BOXNR": 1,
            "OUT_LPN_ID": "",
            "OUT_LPN_QTY": 0,
            "OUT_OBJT_VALUE_PROCESSED": False,
            "OUT_PLC_NEW_VALUE": False,
            "OUT_REPAIR": False,
            "OUT_PO_ID": "",
        }

    async def init_opcua_server(self):
        """Initialize the OPC UA server with all SORT3 tags."""
        logger.info(f"Initializing OPC UA server on port {OPCUA_PORT}...")
        
        self.server = Server()
        await self.server.init()
        
        self.server.set_endpoint(f"opc.tcp://0.0.0.0:{OPCUA_PORT}/freeopcua/server/")
        self.server.set_server_name("SORT3 PLC Simulator")
        
        uri = "http://decospan.com/sort3"
        idx = await self.server.register_namespace(uri)
        
        objects = self.server.nodes.objects
        sort3_obj = await objects.add_object(idx, "OBJT_SORT3")
        sort3_main = await sort3_obj.add_object(idx, "SORT3")
        
        started_po = await sort3_main.add_object(idx, "STARTED_PO")
        await self._create_started_po_nodes(idx, started_po)
        await self._create_custom_attributes_nodes(idx, started_po)
        
        for i in range(1, 7):
            await self._create_srt_station_nodes(idx, started_po, i)
        
        block_output = await sort3_main.add_object(idx, "BLOCK_OUTPUT")
        await self._create_block_output_nodes(idx, block_output)
        
        veneer_stacked = await sort3_main.add_object(idx, "VENEER_STACKED")
        await self._create_veneer_stacked_nodes(idx, veneer_stacked)
        
        logger.info("OPC UA server initialized with all SORT3 tags")

    async def _create_node_with_string_id(self, idx: int, parent: Node, name: str, var_type, default):
        """Create a variable node with an explicit string-based NodeId."""
        nodeid = ua.NodeId(name, idx)
        node = await parent.add_variable(nodeid, name, default, var_type)
        await node.set_writable()
        self.nodes[name] = node
        return node

    async def _create_started_po_nodes(self, idx: int, parent: Node):
        nodes_config = [
            ("SRT_OBJT_NEW_VALUE", ua.VariantType.Boolean, False),
            ("SRT_PLC_VALUE_PROCESSED", ua.VariantType.Boolean, False),
            ("SRT_PO_ID", ua.VariantType.String, ""),
            ("SRT_PO_QTY", ua.VariantType.Int32, 0),
            ("SRT3_IN2", ua.VariantType.String, ""),
            ("ORDER_STATUS", ua.VariantType.Int32, 0),  # 1=active, 0=stopped
        ]
        for name, var_type, default in nodes_config:
            await self._create_node_with_string_id(idx, parent, name, var_type, default)

    async def _create_custom_attributes_nodes(self, idx: int, parent: Node):
        nodes_config = [
            ("SRT_SPEEDBELTTRANSPORT", ua.VariantType.Double, 0.0),
            ("SRT_MAXSHEETSBOX", ua.VariantType.Double, 0.0),
            ("SRT_OPENBOXDISTNACE", ua.VariantType.Double, 0.0),
        ]
        for name, var_type, default in nodes_config:
            await self._create_node_with_string_id(idx, parent, name, var_type, default)

    async def _create_srt_station_nodes(self, idx: int, parent: Node, station: int):
        nodes_config = [
            (f"SRT_{station}_ACTIVE", ua.VariantType.Boolean, False),
            (f"SRT_{station}_CUTTING", ua.VariantType.Boolean, False),
            (f"SRT_{station}_ITEMNAME", ua.VariantType.String, ""),
            (f"SRT_{station}_TAPE", ua.VariantType.Boolean, False),
            (f"SRT_{station}_VENEER_L", ua.VariantType.Double, 0.0),
            (f"SRT_{station}_QTY", ua.VariantType.Int32, 0),  # Box quantity
        ]
        for name, var_type, default in nodes_config:
            await self._create_node_with_string_id(idx, parent, name, var_type, default)

    async def _create_block_output_nodes(self, idx: int, parent: Node):
        nodes_config = [
            ("BB_BOX_BLOCK", ua.VariantType.Boolean, False),
            ("BB_CUTTING", ua.VariantType.Boolean, False),
            ("BB_ITEMNAME", ua.VariantType.String, ""),
            ("BB_OBJT_NEW_VALUE", ua.VariantType.Boolean, False),
            ("BB_OUT_BOXNR", ua.VariantType.Int32, 0),
            ("BB_PLC_VALUE_PROCESSED", ua.VariantType.Boolean, False),
            ("BB_TAPE", ua.VariantType.Boolean, False),
            ("BB_VENEER_L", ua.VariantType.Double, 0.0),
        ]
        for name, var_type, default in nodes_config:
            await self._create_node_with_string_id(idx, parent, name, var_type, default)

    async def _create_veneer_stacked_nodes(self, idx: int, parent: Node):
        nodes_config = [
            ("OUT_BOXFULL", ua.VariantType.Boolean, False),
            ("OUT_BOXNR", ua.VariantType.Int32, 1),
            ("OUT_LPN_ID", ua.VariantType.String, ""),
            ("OUT_LPN_QTY", ua.VariantType.Int32, 0),
            ("OUT_OBJT_VALUE_PROCESSED", ua.VariantType.Boolean, False),
            ("OUT_PLC_NEW_VALUE", ua.VariantType.Boolean, False),
            ("OUT_REPAIR", ua.VariantType.Boolean, False),
            ("OUT_PO_ID", ua.VariantType.String, ""),
        ]
        for name, var_type, default in nodes_config:
            await self._create_node_with_string_id(idx, parent, name, var_type, default)

    async def update_node(self, name: str, value: Any):
        """Update an OPC UA node value."""
        if name in self.nodes:
            try:
                # Convert Python int to Int32 for OPC UA
                if isinstance(value, int) and not isinstance(value, bool):
                    value = ua.Int32(value)
                await self.nodes[name].write_value(value)
                self.state[name] = int(value) if isinstance(value, ua.Int32) else value
                logger.debug(f"Updated {name} = {value}")
            except Exception as e:
                logger.error(f"Failed to update {name} with value {value} (type {type(value).__name__}): {e}")

    async def handle_start_order(self, payload: Dict):
        """Handle start order command."""
        logger.info(f"Processing payload: {payload}")
        
        # Support both 'production_order' and 'po_id' keys
        po_id = payload.get("production_order") or payload.get("po_id")
        po_qty = int(payload.get("quantity") or payload.get("po_qty") or 0)
        stations = payload.get("stations", []) or []

        # Custom attributes: support multiple key names for backwards-compatibility
        speedbelt = float(payload.get("belt_speed") or payload.get("speedbelt") or payload.get("SRT_SPEEDBELTTRANSPORT") or 0.0)
        max_sheets = float(payload.get("max_sheets") or payload.get("maxSheets") or payload.get("max_sheets_box") or payload.get("SRT_MAXSHEETSBOX") or 0.0)
        open_distance = float(payload.get("open_distance") or payload.get("openDistance") or payload.get("SRT_OPENBOXDISTNACE") or 0.0)

        logger.info(f"=== STARTING ORDER: {po_id} ===")
        
        self.current_order = po_id
        self.order_active = True

        # Reset all box quantities
        self.box_quantities = {i: 0 for i in range(1, 7)}
        
        # Update STARTED_PO tags
        await self.update_node("SRT_PO_ID", po_id)
        await self.update_node("SRT_PO_QTY", po_qty)
        # Update custom attributes from payload
        await self.update_node("SRT_SPEEDBELTTRANSPORT", speedbelt)
        await self.update_node("SRT_MAXSHEETSBOX", max_sheets)
        await self.update_node("SRT_OPENBOXDISTNACE", open_distance)
        await self.update_node("SRT_OBJT_NEW_VALUE", True)
        await self.update_node("ORDER_STATUS", 1)  # 1 = active
        
        # Initialize VENEER_STACKED
        await self.update_node("OUT_PO_ID", po_id)
        await self.update_node("OUT_LPN_QTY", 0)
        await self.update_node("OUT_BOXNR", 1)
        await self.update_node("OUT_BOXFULL", False)
        await self.update_node("OUT_PLC_NEW_VALUE", False)
        
        # Initialize stations according to payload 'stations' list.
        # If a station entry is missing or active is False, leave it deactivated and clear values.
        for i in range(1, 7):
            st = stations[i - 1] if len(stations) >= i and isinstance(stations[i - 1], dict) else {}
            active = bool(st.get("active", False))

            await self.update_node(f"SRT_{i}_ACTIVE", active)

            if active:
                # Set optional station properties when active
                itemname = st.get(f"box{i}_material") or st.get("material") or ""
                cutting = bool(st.get("cutting", False))
                tape = bool(st.get("tape", False))
                veneer_l = float(st.get("veneer_l", 0.0) or 0.0)

                await self.update_node(f"SRT_{i}_ITEMNAME", str(itemname))
                await self.update_node(f"SRT_{i}_CUTTING", cutting)
                await self.update_node(f"SRT_{i}_TAPE", tape)
                await self.update_node(f"SRT_{i}_VENEER_L", veneer_l)
                await self.update_node(f"SRT_{i}_QTY", 0)
            else:
                # Ensure deactivated stations are reset/empty
                await self.update_node(f"SRT_{i}_ITEMNAME", "")
                await self.update_node(f"SRT_{i}_CUTTING", False)
                await self.update_node(f"SRT_{i}_TAPE", False)
                await self.update_node(f"SRT_{i}_VENEER_L", 0.0)
                await self.update_node(f"SRT_{i}_QTY", 0)

        logger.info(f"Order {po_id} started - configured stations from payload - simulation running every {SIMULATION_INTERVAL}s")

    async def handle_stop_order(self, payload: Dict = None):
        """Handle stop order command."""
        po_id = self.current_order
        was_active = self.order_active
        
        logger.info("=" * 50)
        logger.info(f"=== STOP ORDER RECEIVED ===")
        logger.info(f"  Payload: {payload}")
        logger.info(f"  Current PO: {po_id}")
        logger.info(f"  Was active: {was_active}")
        logger.info("=" * 50)
        
        # STOP the simulation
        self.order_active = False
        self.current_order = ""
        
        # Reset box quantities
        self.box_quantities = {i: 0 for i in range(1, 7)}
        
        # Reset STARTED_PO
        await self.update_node("SRT_OBJT_NEW_VALUE", False)
        await self.update_node("SRT_PLC_VALUE_PROCESSED", True)
        await self.update_node("SRT_PO_ID", "")
        await self.update_node("SRT_PO_QTY", 0)
        await self.update_node("ORDER_STATUS", 0)  # 0 = stopped
        
        # Reset VENEER_STACKED
        await self.update_node("OUT_PO_ID", "")
        await self.update_node("OUT_LPN_QTY", 0)
        await self.update_node("OUT_PLC_NEW_VALUE", False)

        # Reset custom attributes to defaults
        await self.update_node("SRT_SPEEDBELTTRANSPORT", 0.0)
        await self.update_node("SRT_MAXSHEETSBOX", 0.0)
        await self.update_node("SRT_OPENBOXDISTNACE", 0.0)
        
        # Deactivate all stations
        for i in range(1, 7):
            await self.update_node(f"SRT_{i}_ACTIVE", False)
            await self.update_node(f"SRT_{i}_ITEMNAME", "")
            await self.update_node(f"SRT_{i}_CUTTING", False)
            await self.update_node(f"SRT_{i}_TAPE", False)
            await self.update_node(f"SRT_{i}_VENEER_L", 0.0)
            await self.update_node(f"SRT_{i}_QTY", 0)
        logger.info("=" * 50)
        logger.info("ORDER STOPPED - Simulation paused, all stations deactivated")
        logger.info("=" * 50)

    async def run_simulation_tick(self):
        """Run one tick of the veneer stacking simulation.
        
        All 6 boxes are used simultaneously - randomly select one box
        and increment its quantity.
        """
        import random
        
        if not self.order_active:
            return
        max_sheets = self.state.get("SRT_MAXSHEETSBOX", 0)
        po_id = self.state.get("OUT_PO_ID", "")

        # Determine active stations; if none are active, skip this tick
        active_stations = [i for i in range(1, 7) if bool(self.state.get(f"SRT_{i}_ACTIVE"))]
        if not active_stations:
            logger.debug("No active stations configured - skipping simulation tick")
            return

        # Randomly select one of the active boxes
        selected_box = random.choice(active_stations)
        
        # Get and increment the selected box's quantity
        current_qty = self.box_quantities[selected_box]
        new_qty = current_qty + 1
        self.box_quantities[selected_box] = new_qty
        
        # Check if this box is now full
        box_full = max_sheets > 0 and new_qty >= max_sheets
        
        # Generate LPN ID for this box
        lpn_id = f"LPN-{po_id}-BOX{selected_box:03d}"
        
        # Update VENEER_STACKED nodes
        await self.update_node("OUT_BOXNR", selected_box)
        await self.update_node("OUT_LPN_QTY", new_qty)
        await self.update_node("OUT_LPN_ID", lpn_id)
        await self.update_node("OUT_PLC_NEW_VALUE", True)
        await self.update_node("OUT_BOXFULL", box_full)
        
        # Update the selected box's quantity tag
        await self.update_node(f"SRT_{selected_box}_QTY", new_qty)
        
        # Log with all box quantities
        qty_summary = ", ".join([f"B{i}:{self.box_quantities[i]}" for i in range(1, 7)])
        logger.info(f"VENEER STACKED: Box {selected_box} -> Qty={new_qty}, Full={box_full} | All: [{qty_summary}]")
        
        # Reset PLC_NEW_VALUE after short delay (pulse)
        await asyncio.sleep(0.5)
        await self.update_node("OUT_PLC_NEW_VALUE", False)
        
        # If box is full, reset that box's quantity (simulating box replacement)
        if box_full:
            self.box_quantities[selected_box] = 0
            await self.update_node(f"SRT_{selected_box}_QTY", 0)
            logger.info(f"Box {selected_box} FULL and replaced - quantity reset to 0")

    async def mqtt_listener(self):
        """Listen for MQTT messages using aiomqtt."""
        import aiomqtt
        
        while self.running:
            try:
                logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
                
                async with aiomqtt.Client(MQTT_BROKER, MQTT_PORT, identifier="sort3-simulator") as client:
                    logger.info("Connected to MQTT broker!")
                    
                    # Subscribe to topics
                    await client.subscribe("menen/sort3/start_order")
                    await client.subscribe("menen/sort3/stop_order")
                    logger.info("Subscribed to menen/sort3/start_order and menen/sort3/stop_order")
                    
                    # Publish that we're ready
                    await client.publish("menen/sort3/status", json.dumps({"status": "ready"}))
                    
                    async for message in client.messages:
                        topic = str(message.topic)
                        try:
                            payload = json.loads(message.payload.decode()) if message.payload else {}
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in message, using raw payload")
                            payload = {"raw": message.payload.decode()}
                        
                        logger.info(f"MQTT received: {topic} -> {payload}")
                        
                        try:
                            if topic == "menen/sort3/start_order":
                                await self.handle_start_order(payload)
                            elif topic == "menen/sort3/stop_order":
                                await self.handle_stop_order(payload)
                        except Exception as e:
                            logger.error(f"Error handling message on {topic}: {e}")
                            
            except aiomqtt.MqttError as e:
                logger.error(f"MQTT error: {e} - reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"MQTT listener error: {e} - reconnecting in 5s...")
                await asyncio.sleep(5)

    async def simulation_loop(self):
        """Main simulation loop."""
        logger.info(f"Simulation loop started (interval: {SIMULATION_INTERVAL}s)")
        
        while self.running:
            await asyncio.sleep(SIMULATION_INTERVAL)
            if self.order_active:
                await self.run_simulation_tick()

    async def start(self):
        """Start the simulator."""
        self.running = True
        
        # Initialize and start OPC UA server
        await self.init_opcua_server()
        await self.server.start()
        logger.info(f"OPC UA server started on opc.tcp://0.0.0.0:{OPCUA_PORT}")
        
        # Start MQTT listener and simulation loop concurrently
        mqtt_task = asyncio.create_task(self.mqtt_listener())
        sim_task = asyncio.create_task(self.simulation_loop())
        
        logger.info("=" * 50)
        logger.info("SORT3 Simulator Ready!")
        logger.info(f"  OPC UA: opc.tcp://localhost:{OPCUA_PORT}")
        logger.info(f"  MQTT: {MQTT_BROKER}:{MQTT_PORT}")
        logger.info("  Topics:")
        logger.info("    - menen/sort3/start_order")
        logger.info("    - menen/sort3/stop_order")
        logger.info("=" * 50)
        
        # Wait for tasks
        try:
            await asyncio.gather(mqtt_task, sim_task)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        """Stop the simulator."""
        logger.info("Stopping simulator...")
        self.running = False
        self.order_active = False
        
        if self.server:
            await self.server.stop()
        
        logger.info("Simulator stopped")


async def main():
    """Main entry point."""
    simulator = Sort3Simulator()
    
    try:
        await simulator.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await simulator.stop()


if __name__ == "__main__":
    asyncio.run(main())
