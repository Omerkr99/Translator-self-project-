import struct

from gcrts.cdrom_driver_map import (
    CDROM_COMMAND_PTR_ADDR,
    CDROM_COMMAND_REG,
    CDROM_INDEX_PTR_ADDR,
    CDROM_INDEX_REG,
    CDROM_PARAM_PTR_ADDR,
    CDROM_PARAM_REG,
    CDROM_REQUEST_PTR_ADDR,
    CDROM_REQUEST_REG,
    SETFILTER_COMMAND,
    CdromDriverConfidence,
    CdromDriverMap,
    resolve_cdrom_driver_map,
)


def _reader(ram: dict):
    return lambda addr, length: ram.get(addr)


def _real_ram() -> dict:
    """The exact live-read values from this session: all 4 pointer
    variables hold the real PS1 CD-ROM hardware register addresses."""
    return {
        CDROM_INDEX_PTR_ADDR: struct.pack("<I", CDROM_INDEX_REG),
        CDROM_COMMAND_PTR_ADDR: struct.pack("<I", CDROM_COMMAND_REG),
        CDROM_PARAM_PTR_ADDR: struct.pack("<I", CDROM_PARAM_REG),
        CDROM_REQUEST_PTR_ADDR: struct.pack("<I", CDROM_REQUEST_REG),
    }


def test_setfilter_command_is_the_publicly_documented_value():
    """0x0D, per psx-spx / LibPSn00b: "Setfilter -- Sets XA audio
    filter" -- public documentation, not this session's own guess."""
    assert SETFILTER_COMMAND == 0x0D


def test_resolve_live_verified_when_all_pointers_match_real_hardware():
    driver = resolve_cdrom_driver_map(_reader(_real_ram()))
    assert driver.index_reg_ptr == CDROM_INDEX_REG
    assert driver.command_reg_ptr == CDROM_COMMAND_REG
    assert driver.param_reg_ptr == CDROM_PARAM_REG
    assert driver.request_reg_ptr == CDROM_REQUEST_REG
    assert driver.confidence == CdromDriverConfidence.LIVE_VERIFIED


def test_resolve_unknown_when_a_pointer_does_not_match_real_hardware():
    ram = _real_ram()
    ram[CDROM_COMMAND_PTR_ADDR] = struct.pack("<I", 0xDEADBEEF)
    driver = resolve_cdrom_driver_map(_reader(ram))
    assert driver.command_reg_ptr == 0xDEADBEEF
    assert driver.confidence == CdromDriverConfidence.UNKNOWN


def test_resolve_unknown_when_pointers_unreadable():
    driver = resolve_cdrom_driver_map(_reader({}))
    assert driver.index_reg_ptr is None
    assert driver.confidence == CdromDriverConfidence.UNKNOWN


def test_round_trips_through_dict():
    driver = resolve_cdrom_driver_map(_reader(_real_ram()))
    restored = CdromDriverMap.from_dict(driver.to_dict())
    assert restored == driver
