"""Donkey Kong 64 client for Archipelago."""

import ModuleUpdate

ModuleUpdate.update()

import Utils

if __name__ == "__main__":
    Utils.init_logging("DK64Context", exception_logger="Client")
import json
import asyncio
import colorama
import time
import typing
from client.common import DK64MemoryMap, create_task_log_exception, check_version
from client.pj64 import PJ64Client
from client.items import item_ids, item_names_to_id
from client.check_flag_locations import location_flag_to_name, location_name_to_flag
from client.ap_check_ids import check_id_to_name, check_names_to_id
from CommonClient import CommonContext, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus


class DK64Client:
    """Client for Donkey Kong 64."""

    n64_client = PJ64Client()
    tracker = None
    game = None
    auth = None
    recvd_checks = []
    players = None
    stop_bizhawk_spam = False
    remaining_checks = []
    flag_lookup = None
    seed_started = False
    sent_checks = []
    item_names = None
    memory_pointer = None
    _purchase_cache = {}
    deathlink_debounce = True
    pending_deathlink = False
    send_mode = 1
    ENABLE_DEATHLINK = False
    current_speed = 130

    async def wait_for_pj64(self):
        """Wait for PJ64 to connect to the game."""
        clear_waiting_message = True
        if not self.stop_bizhawk_spam:
            logger.info("Waiting on connection to PJ64...")
            self.stop_bizhawk_spam = True

        while True:
            try:
                socket_connected = False
                valid_rom = self.n64_client.validate_rom(self.game, DK64MemoryMap.memory_pointer)
                if self.n64_client.socket is not None and not socket_connected:
                    logger.info("Connected to PJ64")
                    socket_connected = True
                while not valid_rom:
                    if self.n64_client.socket is not None and not socket_connected:
                        logger.info("Connected to PJ64")
                        socket_connected = True
                    if clear_waiting_message:
                        logger.info("Waiting on valid ROM...")
                        clear_waiting_message = False
                    await asyncio.sleep(1.0)
                    valid_rom = self.n64_client.validate_rom(self.game, DK64MemoryMap.memory_pointer)
                self.stop_bizhawk_spam = False
                logger.info("PJ64 Connected to ROM!")
                return
            except (BlockingIOError, TimeoutError, ConnectionResetError):
                await asyncio.sleep(1.0)
                pass

    def check_safe_gameplay(self):
        """Check if the game is in a valid state for sending items."""
        current_gamemode = self.n64_client.read_u8(DK64MemoryMap.CurrentGamemode)
        next_gamemode = self.n64_client.read_u8(DK64MemoryMap.NextGamemode)
        return current_gamemode in [6, 0xD] and next_gamemode in [6, 0xD]

    def safe_to_send(self):
        """Check if it's safe to send an item."""
        countdown_value = self.n64_client.read_u8(self.memory_pointer + DK64MemoryMap.safety_text_timer)
        return countdown_value == 0

    async def validate_client_connection(self):
        """Validate the client connection."""
        if not self.memory_pointer:
            self.memory_pointer = self.n64_client.read_u32(DK64MemoryMap.memory_pointer)
        self.n64_client.write_u8(self.memory_pointer + DK64MemoryMap.connection, 0xFF)

    def send_message(self, item_name, player_name, event_type="from"):
        """Send a message to the game."""

        def sanitize_and_trim(input_string, max_length=0x20):
            sanitized = "".join(e for e in input_string if e.isalnum() or e == " ").strip()
            return sanitized[:max_length]

        stripped_item_name = sanitize_and_trim(item_name)
        stripped_player_name = sanitize_and_trim(player_name)
        self.n64_client.write_bytestring(self.memory_pointer + DK64MemoryMap.fed_string, f"{stripped_item_name}")
        self.n64_client.write_bytestring(self.memory_pointer + DK64MemoryMap.fed_subtitle, f"{event_type} {stripped_player_name}")

    def set_speed(self, speed: int):
        """Set the speed of the display text in game."""
        self.n64_client.write_u8(self.memory_pointer + DK64MemoryMap.text_timer, speed)

    async def recved_item_from_ap(self, item_id, item_name, from_player, index):
        """Handle an item received from Archipelago."""
        # Don't allow getting an item until you've got your first check
        if not self.started_file():
            return

        # Spin until we either:
        # get an exception from a bad read (emu shut down or reset)
        # beat the game
        # the client handles the last pending item
        status = self.safe_to_send()
        while not status:
            await asyncio.sleep(0.1)
            status = self.safe_to_send()
        next_index = index + 1
        self.n64_client.write_u8(self.memory_pointer + DK64MemoryMap.counter_offset, next_index)
        item_data = item_ids.get(item_id)
        if item_data:
            if self.send_mode == 6:
                if self.current_speed != 130:
                    self.set_speed(130)
                    self.current_speed = 130
                # Progression only, no speed changes
                if item_data.get("progression", False):
                    self.send_message(item_name, from_player, "from")
            elif self.send_mode == 5:
                if self.current_speed != 130:
                    self.set_speed(130)
                    self.current_speed = 130
                # Extended whitelist, no speed changes
                if item_data.get("progression", False):
                    self.send_message(item_name, from_player, "from")
                elif item_data.get("extended_whitelist", False):
                    self.send_message(item_name, from_player, "from")
            elif self.send_mode == 4:
                # Display both default and extended whitelist items
                # But display just the extended whitelist items at a faster speed
                if item_data.get("progression", False):
                    if self.current_speed != 130:
                        self.set_speed(130)
                        self.current_speed = 130
                    self.send_message(item_name, from_player, "from")
                elif item_data.get("extended_whitelist", False):
                    if self.current_speed != 50:
                        self.set_speed(50)
                        self.current_speed = 50
                    self.send_message(item_name, from_player, "from")
            elif self.send_mode == 3:
                # Send everything super fast on both whitelist and extended whitelist
                if self.current_speed != 50:
                    self.current_speed = 50
                    self.set_speed(50)
                if item_data.get("progression", False):
                    self.send_message(item_name, from_player, "from")
                elif item_data.get("extended_whitelist", False):
                    self.send_message(item_name, from_player, "from")
            elif self.send_mode == 2:
                # If we have more than 5 items queued, from 130 to 50, do a percentage of the total items
                # But only display progression items, discard the rest
                length = len(self.recvd_checks) - index
                if length <= 5:
                    if self.current_speed != 130:
                        self.current_speed = 130
                        self.set_speed(130)
                    if item_data.get("progression", False):
                        self.send_message(item_name, from_player, "from")
                    elif item_data.get("extended_whitelist", False):
                        self.send_message(item_name, from_player, "from")
                else:
                    speed = round(130 - (80 / length))
                    if speed < 50:
                        speed = 50
                    if self.current_speed != speed:
                        self.current_speed = speed
                        self.set_speed(speed)
                    if item_data.get("progression", False):
                        self.send_message(item_name, from_player, "from")
            elif self.send_mode == 1:
                # If we have more than 5 items queued, from 130 to 50, do a percentage of the total items
                # If we have 5 or less, do 130
                length = len(self.recvd_checks) - index
                if length <= 5:
                    if self.current_speed != 130:
                        self.current_speed = 130
                        self.set_speed(130)
                else:
                    speed = round(130 - (80 / length))
                    if speed < 50:
                        speed = 50
                    if self.current_speed != speed:
                        self.current_speed = speed
                        self.set_speed(speed)
                if item_data.get("progression", False):
                    self.send_message(item_name, from_player, "from")
                elif item_data.get("extended_whitelist", False):
                    self.send_message(item_name, from_player, "from")
            else:
                raise Exception("Invalid message mode")

            if item_data.get("flag_id", None) is not None:
                self.setFlag(item_data.get("flag_id"))
            elif item_data.get("fed_id", None) is not None:
                await self.writeFedData(item_data.get("fed_id"))
            else:
                logger.warning(f"Item {item_name} has no flag or fed id")

    async def writeFedData(self, fed_item):
        """Write the fed item data to the game."""
        current_fed_item = self.n64_client.read_u32(self.memory_pointer + DK64MemoryMap.arch_items)
        # If item is being processed, don't update
        while current_fed_item != 0:
            current_fed_item = self.n64_client.read_u32(self.memory_pointer + DK64MemoryMap.arch_items)
            await asyncio.sleep(0.1)
            if current_fed_item == 0:
                break
        self.n64_client.write_u8(self.memory_pointer + 0x7, fed_item)

    def _getShopStatus(self, p_type: int, p_value: int, p_kong: int) -> bool:
        """Get the status of a shop item."""
        if p_type == 0xFFFF:
            return False
        if p_value == 0:
            return False
        if p_kong > 4:
            p_kong = 0
        kong_base = 0x807FC950 + (p_kong * 0x5E)
        if p_type < 5:
            val = self.n64_client.read_u8(kong_base + p_type)
            if p_type in (1, 3):
                # Slam, Ammo Belt
                return val >= p_type
            else:
                return (val & (1 << (p_value - 1))) != 0
        else:
            return self.readFlag(p_value) != 0

    def _build_flag_lookup(self):
        """Cache flag mappings to avoid repeated reads."""
        self.flag_lookup = {}
        for flut_index in range(0x400):
            raw_flag = self.n64_client.read_u16(0x807E2EE0 + (4 * flut_index))
            if raw_flag == 0xFFFF:
                break
            target_flag = self.n64_client.read_u16(0x807E2EE0 + (4 * flut_index) + 2)
            self.flag_lookup[raw_flag] = target_flag

    def getMoveStatus(self, move_flag: int) -> bool:
        """Get the status of a move."""
        item_kong = (move_flag >> 12) & 7
        if item_kong > 4:
            item_kong = 0
        item_type = (move_flag >> 8) & 15
        if item_type == 7:
            return True
        item_index = move_flag & 0xFF
        address = 0x807FC950 + (0x5E * item_kong) + item_type
        value = self.n64_client.read_u8(address)
        offset = 0
        if item_index > 0:
            offset = item_index - 1
        return ((value >> offset) & 1) != 0

    def getCheckStatus(self, check_type, flag_index=None, shop_index=None, level_index=None, kong_index=None, _bulk_read_dict={}) -> bool:
        """Get the status of a check."""
        # shop_index: 0 = cranky, 1 = funky, 2 = candy, 3 = bfi
        # flag_index: as expected
        if check_type == "shop":
            cache_key = (shop_index, kong_index, level_index)
            if cache_key in self._purchase_cache:
                # Retrieve cached values
                purchase_type, purchase_value, purchase_kong = self._purchase_cache[cache_key]
            else:
                # Calculate header and read values
                if shop_index == 3:
                    header = 0x807FF6E8
                else:
                    header = 0x807FF400 + (shop_index * 0xF0) + (kong_index * 0x30) + (level_index * 6)
                purchase_type = self.n64_client.read_u16(header + 0)
                purchase_value = self.n64_client.read_u16(header + 2)
                purchase_kong = self.n64_client.read_u8(header + 4)
                # Cache the values
                self._purchase_cache[cache_key] = (purchase_type, purchase_value, purchase_kong)

            return self._getShopStatus(purchase_type, purchase_value, purchase_kong)
        else:
            if self.flag_lookup is None:
                self._build_flag_lookup()
            # Check if the flag exists in the lookup table
            if self.flag_lookup.get(flag_index):
                target_flag = self.flag_lookup[flag_index]
                if target_flag & 0x8000:
                    return self.getMoveStatus(target_flag)
                elif target_flag == 0xFFFE:
                    has_camera = self.readFlag(0x2FD) != 0
                    has_shockwave = self.readFlag(0x179) != 0
                    return has_camera and has_shockwave
                return _bulk_read_dict.get(target_flag) != 0
            else:
                return _bulk_read_dict.get(flag_index) != 0

    def bulk_lookup(self, flag_index, _bulk_read_dict):
        """Bulk lookup of flags."""
        if self.flag_lookup is None:
            self._build_flag_lookup()
        if self.flag_lookup.get(flag_index):
            target_flag = self.flag_lookup[flag_index]
            byte_index = target_flag >> 3
            offset = DK64MemoryMap.EEPROM + byte_index
            _bulk_read_dict[target_flag] = offset
        else:
            byte_index = flag_index >> 3
            offset = DK64MemoryMap.EEPROM + byte_index
            _bulk_read_dict[flag_index] = offset

    async def readChecks(self, cb):
        """Run checks in parallel using asyncio."""
        new_checks = []
        _bulk_read_dict = {}
        for id in self.remaining_checks:
            name = check_id_to_name.get(id)
            # Try to get the check via location_name_to_flag
            check = location_name_to_flag.get(name)
            if check:
                self.bulk_lookup(check, _bulk_read_dict)
            # If its not there using the id lets try to get it via item_ids
            else:
                check = item_ids.get(id)
                if check:
                    flag_id = check.get("flag_id")
                    if not flag_id:
                        # logger.error(f"Item {name} has no flag_id")
                        continue
                    else:
                        self.bulk_lookup(flag_id, _bulk_read_dict)
        dict_data = self.n64_client.read_dict(_bulk_read_dict)
        # Json loads the dict_data
        dict_data = json.loads(dict_data)
        # For each item in the dict, the key is the index the value is the val for byte_shift. Keep the key the same but set the value to the result of byte_shift
        for key, val in dict_data.items():
            shift = int(key) & 7
            flag_status = (int(val[0]) >> shift) & 1
            _bulk_read_dict[int(key)] = flag_status
        for id in self.remaining_checks[:]:
            name = check_id_to_name.get(id)
            # Try to get the check via location_name_to_flag
            check = location_name_to_flag.get(name)
            if check:
                # Assuming we did find it in location_name_to_flag
                check_status = self.getCheckStatus("location", check, _bulk_read_dict=_bulk_read_dict)
                if check_status:
                    # logger.info(f"Found {name} via location_name_to_flag")
                    self.remaining_checks.remove(id)
                    new_checks.append(id)
            # If its not there using the id lets try to get it via item_ids
            else:
                check = item_ids.get(id)
                if check:
                    flag_id = check.get("flag_id")
                    if not flag_id:
                        # logger.error(f"Item {name} has no flag_id")
                        continue
                    else:
                        check_status = self.getCheckStatus("location", flag_id, _bulk_read_dict=_bulk_read_dict)
                        if check_status:
                            # logger.info(f"Found {name} via item_ids")
                            self.remaining_checks.remove(id)
                            new_checks.append(id)
                else:
                    # If the content is 3 parts separated by a space, we can assume it's a shop check
                    content = name.split(" ")
                    if name == "The Banana Fairy's Gift":
                        check_status = self.getCheckStatus("shop", None, 3, None, None)
                        if check_status:
                            # logger.info(f"Found {name} via location_name_to_flag")
                            self.remaining_checks.remove(id)
                            new_checks.append(id)
                        continue
                    elif len(content) == 3:
                        level_mapping = {"Japes": 0, "Aztec": 1, "Factory": 2, "Galleon": 3, "Forest": 4, "Caves": 5, "Castle": 6, "Isles": 7}
                        shop_mapping = {"Cranky": 0, "Funky": 1, "Candy": 2}
                        kong_mapping = {"Donkey": 0, "Diddy": 1, "Lanky": 2, "Tiny": 3, "Chunky": 4}

                        level_index = level_mapping.get(content[0])
                        shop_index = shop_mapping.get(content[1])
                        kong_index = kong_mapping.get(content[2])

                        # If any of these are not set, continue
                        if level_index is None or shop_index is None or kong_index is None:
                            continue

                        check_status = self.getCheckStatus("shop", None, shop_index, level_index, kong_index)
                        if check_status:
                            # print(f"Found {name} via shop check")
                            self.remaining_checks.remove(id)
                            new_checks.append(id)
                        continue
                continue

        if new_checks:
            cb(new_checks)
        return True

    async def reset_auth(self):
        """Reset the auth by looking up a username from ROM."""
        username = self.n64_client.read_bytestring(0x1FF3000 + 0xB0000000, 16).strip()
        # Strip all trailing \x00
        username = username.replace("\x00", "")
        self.auth = username
        # TODO: Maybe in some random case we try to get the username manually, but thats a problem for later
        # await self.get_username()

    def started_file(self):
        """Check if the file has been started."""
        # Checks to see if the file has been started
        if not self.seed_started:
            status = self.readFlag(0) == 1
            if status:
                self.seed_started = True
            return status
        return True

    should_reset_auth = False

    def setFlag(self, index: int) -> int:
        """Set a flag in the game."""
        byte_index = index >> 3
        shift = index & 7
        offset = DK64MemoryMap.EEPROM + byte_index
        val = self.n64_client.read_u8(offset)
        self.n64_client.write_u8(offset, val | (1 << shift))
        return 1

    def readFlag(self, index: int) -> int:
        """Read a flag in the game."""
        byte_index = index >> 3
        shift = index & 7
        offset = DK64MemoryMap.EEPROM + byte_index
        val = self.n64_client.read_u8(offset)
        return (val >> shift) & 1

    async def wait_for_game_ready(self):
        """Wait for the game to be ready."""
        logger.info("Waiting on game to be in valid state...")
        while not self.check_safe_gameplay():
            if self.should_reset_auth:
                self.should_reset_auth = False
                raise Exception("Resetting due to wrong archipelago server")
        logger.info("Game connection ready!")

    async def is_victory(self):
        """Check if the game is in a victory state."""
        return self.readFlag(DK64MemoryMap.end_credits) == 1

    def get_current_deliver_count(self):
        """Get the current deliver count."""
        return self.n64_client.read_u8(self.memory_pointer + DK64MemoryMap.counter_offset)

    async def main_tick(self, item_get_cb, win_cb, deathlink_cb):
        """Game loop tick."""
        await self.readChecks(item_get_cb)
        # await self.item_tracker.readItems()
        if await self.is_victory():
            await win_cb()

        def check_safe_death():
            """Check if it's safe to send a death."""
            return self.n64_client.read_u8(self.memory_pointer + DK64MemoryMap.can_die) != 1

        if self.ENABLE_DEATHLINK:
            death_state = self.n64_client.read_u8(self.memory_pointer + DK64MemoryMap.send_death)
            if self.deathlink_debounce and death_state == 0:
                self.deathlink_debounce = False
            elif not self.deathlink_debounce and death_state == 1:
                # logger.info("YOU DIED.")
                await deathlink_cb()
                self.n64_client.write_u8(self.memory_pointer + DK64MemoryMap.send_death, 0)
                self.deathlink_debounce = True

            if self.pending_deathlink:
                logger.info("Got a deathlink")
                while check_safe_death():
                    await asyncio.sleep(0.1)
                self.n64_client.write_u8(self.memory_pointer + DK64MemoryMap.receive_death, 1)
                self.n64_client.write_u8(self.memory_pointer + DK64MemoryMap.send_death, 0)
                self.pending_deathlink = False
                self.deathlink_debounce = True
                await asyncio.sleep(5)

        current_deliver_count = self.get_current_deliver_count()
        # If current_deliver_count is None
        if current_deliver_count is None:
            # Reset the current_deliver_count to 0
            current_deliver_count = 0

        if len(self.recvd_checks) > current_deliver_count:
            # Get the next item in recvd_checks
            item = self.recvd_checks[current_deliver_count]
            item_name = self.item_names.lookup_in_game(item.item)
            player_name = self.players.get(item.player)
            await self.recved_item_from_ap(item.item, item_name, player_name, current_deliver_count)

        if len(self.sent_checks) > 0:
            cloned_checks = self.sent_checks.copy()
            for item in cloned_checks:
                status = self.safe_to_send()
                while not status:
                    await asyncio.sleep(0.1)
                    status = self.safe_to_send()
                # Strip out special characters from item name
                item_name = item[0]
                sender = item[1]
                self.send_message(item_name, sender, "to")
                self.sent_checks.remove(item)


class DK64Context(CommonContext):
    """Context for Donkey Kong 64."""

    tags = {"AP"}
    game = "Donkey Kong 64"
    la_task = None
    found_checks = []
    last_resend = time.time()
    remaining_checks = list(check_id_to_name.keys())
    ENABLE_DEATHLINK = False

    won = False

    def __init__(self, server_address: typing.Optional[str], password: typing.Optional[str]) -> None:
        """Initialize the DK64 context."""
        self.client = DK64Client()
        self.client.game = self.game.upper()
        self.client.remaining_checks = self.remaining_checks
        self.slot_data = {}

        super().__init__(server_address, password)

    def run_gui(self) -> None:
        """Run the GUI."""
        from kvui import GameManager

        class DK64Manager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago"),
                ("Tracker", "Tracker"),
            ]
            base_title = "Archipelago Donkey Kong 64 Client"

            def build(self):
                b = super().build()
                return b

        self.ui = DK64Manager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    async def send_checks(self):
        """Send the checks to the server."""
        message = [{"cmd": "LocationChecks", "locations": self.found_checks}]
        await self.send_msgs(message)

    had_invalid_slot_data: typing.Optional[bool] = None

    def event_invalid_slot(self):
        """Handle an invalid slot event."""
        # The next time we try to connect, reset the game loop for new auth
        self.had_invalid_slot_data = True
        self.auth = None
        # Don't try to autoreconnect, it will just fail
        self.disconnected_intentionally = True
        CommonContext.event_invalid_slot(self)

    async def send_victory(self):
        """Send a victory message."""
        if not self.won:
            message = [{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]
            logger.info("victory!")
            await self.send_msgs(message)
            self.won = True

    def new_checks(self, item_ids):
        """Handle new checks."""
        self.found_checks += item_ids
        create_task_log_exception(self.send_checks())

    async def server_auth(self, password_requested: bool = False):
        """Authenticate with the server."""
        if password_requested and not self.password:
            await super(DK64Context, self).server_auth(password_requested)
        if self.had_invalid_slot_data:
            # We are connecting when previously we had the wrong ROM or server - just in case
            # re-read the ROM so that if the user had the correct address but wrong ROM, we
            # allow a successful reconnect
            self.client.should_reset_auth = True
            self.had_invalid_slot_data = False
            self.client.recvd_checks.clear()

        while self.client.auth is None:
            await asyncio.sleep(0.1)

            # Just return if we're closing
            if self.exit_event.is_set():
                return

        self.auth = self.client.auth
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        """Handle a package."""
        self.client.item_names = self.item_names
        if cmd == "Connected":
            self.game = self.slot_info[self.slot].game
            self.slot_data = args.get("slot_data", {})
            self.client.players = self.player_names
            self.client.recvd_checks.clear()

        if cmd == "ReceivedItems":
            for index, item in enumerate(args["items"], start=args["index"]):
                self.client.recvd_checks.append(item)
        if cmd == "PrintJSON":
            # For each item in the list, if theres a LocationID in it, check if the player is our slot
            if args.get("type") == "ItemSend":
                sender = args.get("item").player == self.slot
                player = args.get("receiving")
                item_name = self.item_names.lookup_in_game(args.get("item").item, self.slot_info[player].game)
                if sender and player != self.slot:
                    player_name = self.player_names.get(player)
                    self.client.sent_checks.append((item_name, player_name))

    async def sync(self):
        """Sync the game."""
        sync_msg = [{"cmd": "Sync"}]
        await self.send_msgs(sync_msg)

    async def send_deathlink(self):
        """Send a deathlink."""
        if self.ENABLE_DEATHLINK:
            self.last_death_link = time.time()
            player_name = self.player_names.get(self.slot)
            await self.send_death(player_name + " slipped on a banana")

    def on_deathlink(self, data: typing.Dict[str, typing.Any]) -> None:
        """Handle a deathlink."""
        if self.ENABLE_DEATHLINK:
            self.client.pending_deathlink = True

    async def run_game_loop(self):
        """Run the game loop."""

        async def victory():
            """Handle a victory."""
            await self.send_victory()

        async def deathlink():
            """Handle a deathlink."""
            await self.send_deathlink()

        def on_item_get(dk64_checks):
            """Handle an item get."""
            built_checks_list = []
            for check in dk64_checks:
                check_name = check_id_to_name.get(check)
                if check_name:
                    built_checks_list.append(check)
                    continue
                item = item_ids.get(check)
                if item:
                    built_checks_list.append(check)
            self.new_checks(built_checks_list)

        # yield to allow UI to start
        await asyncio.sleep(0)
        while True:
            await asyncio.sleep(3)

            try:
                if not self.client.stop_bizhawk_spam:
                    logger.info("(Re)Starting game loop")
                self.found_checks.clear()
                # On restart of game loop, clear all checks, just in case we swapped ROMs
                # this isn't totally neccessary, but is extra safety against cross-ROM contamination
                self.client.recvd_checks.clear()
                await self.client.wait_for_pj64()

                async def disconnect_check():
                    if self.auth and self.client.auth != self.auth:
                        self.auth = self.client.auth
                        # It would be neat to reconnect here, but connection needs this loop to be running
                        logger.info("Detected new ROM, disconnecting...")
                        await self.disconnect()

                while self.auth is None:
                    await self.client.validate_client_connection()
                    await self.client.reset_auth()
                    await disconnect_check()
                    await asyncio.sleep(3)

                if not self.client.recvd_checks:
                    await self.sync()

                await asyncio.sleep(1.0)
                while True:
                    await self.client.reset_auth()
                    await disconnect_check()
                    await self.client.validate_client_connection()
                    status = self.client.check_safe_gameplay()
                    if status is False:
                        await asyncio.sleep(0.5)
                        continue
                    await self.client.main_tick(on_item_get, victory, deathlink)
                    await asyncio.sleep(1)
                    now = time.time()
                    if self.last_resend + 0.5 < now:
                        self.last_resend = now
                        await self.send_checks()
                    if self.client.should_reset_auth:
                        self.client.should_reset_auth = False
                        raise Exception("Resetting due to wrong archipelago server")
            # There is 100% better ways to handle this exception, but for now this will do to allow us to exit the loop
            except Exception as e:
                print(e)
                await asyncio.sleep(1.0)


def launch():
    """Launch the DK64 client."""

    async def main():
        """Entrypoint of codebase."""
        parser = get_base_parser(description="Donkey Kong 64 Client.")
        parser.add_argument("--url", help="Archipelago connection url")

        args = parser.parse_args()
        check_version()

        ctx = DK64Context(args.connect, args.password)
        ctx.items_handling = 0b001
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if ctx.slot_data.get("death_link"):
            if "DeathLink" not in ctx.tags:
                await ctx.update_death_link(True)
                ctx.ENABLE_DEATHLINK = True
                ctx.client.ENABLE_DEATHLINK = True
        if ctx.slot_data.get("receive_notifications"):
            ctx.client.send_mode = ctx.slot_data.get("receive_notifications")
        ctx.la_task = create_task_log_exception(ctx.run_game_loop())
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        await ctx.exit_event.wait()
        await ctx.shutdown()

    colorama.init()
    asyncio.run(main())
    colorama.deinit()


if __name__ == "__main__":
    launch()
