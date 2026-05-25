"""Register Allocator — assigns physical registers to virtual registers."""
import configparser
from pathlib import Path


CONFIG_PATH = Path("/app/runtime/config/allocator.ini")


class RegisterAllocator:
    """Linear-scan style register allocator with spill support."""
    
    def __init__(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)
        
        self._max_registers = config.getint("allocator", "max_registers")
        self._spill_threshold = config.getint("allocator", "spill_threshold")
        
        # Parse supported register classes
        raw_classes = config.get("allocator", "register_classes")
        self._register_classes = set(raw_classes.split(","))
        
        # Physical register pools per class
        self._pools = {}
        for rc in self._register_classes:
            self._pools[rc] = list(range(self._max_registers))
    
    def allocate(self, scheduled_instructions, pressure_map):
        """
        Allocate physical registers to all virtual destinations.
        
        Uses pressure to decide when to spill. If pressure for a class
        exceeds spill_threshold, subsequent allocations in that class
        get spill slots instead of physical registers.
        """
        allocation_map = {}
        counters = {rc: 0 for rc in self._register_classes}
        spill_counter = 0
        
        for instr in scheduled_instructions:
            dest = instr["dest"]
            if dest is None:
                continue
            
            reg_class = instr["register_class"]
            
            # Check if this register class is supported
            if reg_class not in self._register_classes:
                # Unsupported class — assign to spill
                allocation_map[dest] = {
                    "type": "spill",
                    "location": f"stack_{spill_counter}",
                    "register_class": reg_class,
                }
                spill_counter += 1
                continue
            
            # Check pressure against threshold
            class_pressure = pressure_map.get(reg_class, 0)
            
            if class_pressure > self._spill_threshold:
                # High pressure — spill
                allocation_map[dest] = {
                    "type": "spill",
                    "location": f"stack_{spill_counter}",
                    "register_class": reg_class,
                }
                spill_counter += 1
            else:
                # Normal allocation
                reg_num = counters[reg_class] % self._max_registers
                counters[reg_class] += 1
                allocation_map[dest] = {
                    "type": "register",
                    "location": f"{reg_class}{reg_num}",
                    "register_class": reg_class,
                }
        
        return allocation_map
