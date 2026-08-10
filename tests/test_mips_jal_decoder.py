import pytest

from gcrts.mips_jal_decoder import (
    CallSiteExpectation,
    CallSiteMismatchError,
    InvalidJalInstructionError,
    JalDecodeResult,
    decode_jal,
    decode_jal_bytes,
    opcode_of,
    validate_call_site,
)


# ---------------------------------------------------------------------------
# Ground-truth values below are independently recomputed (not copied from any
# hand calculation) for real instruction words captured live this session --
# see EXPERIMENT_PLAN.md for the narrative these correspond to.
# ---------------------------------------------------------------------------


def test_decode_jal_matches_this_sessions_actual_mistake_case():
    # 0x8003a90c / word 0x0c00ec89: hand-decoded (WRONGLY) as 0x8003B1E4
    # during live investigation; the correct target is 0x8003B224. This
    # is the literal case that motivated building this module.
    result = decode_jal(0x8003A90C, 0x0C00EC89)
    assert result.target == 0x8003B224
    assert result.return_address == 0x8003A914
    assert result.target != 0x8003B1E4  # the actual wrong value produced by hand


def test_decode_jal_matches_candidate_a_call_site():
    # 0x8003a900 / word 0x0c00ebff -> confirmed live this session as
    # candidate A's real entry (0x8003AFFC), return address 0x8003A908.
    result = decode_jal(0x8003A900, 0x0C00EBFF)
    assert result.target == 0x8003AFFC
    assert result.return_address == 0x8003A908


def test_decode_jal_matches_mode_handler_call_site():
    # 0x80038ca0 / synthetic word encoding target 0x8003a6c0 -> return
    # address 0x80038ca8, matching this session's own live-confirmed
    # ra for the chapter-1 mode-handler entry.
    result = decode_jal(0x80038CA0, 0x0C00E9B0)
    assert result.target == 0x8003A6C0
    assert result.return_address == 0x80038CA8


def test_return_address_is_pc_plus_8_not_pc_plus_4():
    # The other concrete mistake this session made and had to re-catch.
    result = decode_jal(0x80048410, 0x0C000000)
    assert result.return_address == 0x80048410 + 8
    assert result.return_address != 0x80048410 + 4


def test_decode_jal_rejects_non_jal_opcode():
    # 0x27bdffe0 is "addiu $sp,$sp,-0x20" (opcode 0x09), not J/JAL.
    with pytest.raises(InvalidJalInstructionError):
        decode_jal(0x8004A36C, 0x27BDFFE0)


def test_decode_jal_accepts_j_only_with_allow_j_true():
    # A J instruction (opcode 0x02) targeting 0x8003B034, encountered
    # while tracing candidate A's own body this session.
    j_word = 0x0800EC0D
    with pytest.raises(InvalidJalInstructionError):
        decode_jal(0x8003B028, j_word)
    result = decode_jal(0x8003B028, j_word, allow_j=True)
    assert result.is_j
    assert not result.is_jal
    assert result.target == 0x8003B034


def test_opcode_of_extracts_top_six_bits():
    assert opcode_of(0x0C00EC89) == 0x03  # JAL
    assert opcode_of(0x27BDFFE0) == 0x09  # ADDIU
    assert opcode_of(0x0800EC0D) == 0x02  # J


def test_decode_jal_bytes_matches_decode_jal():
    raw = (0x0C00EC89).to_bytes(4, "little")
    from_bytes = decode_jal_bytes(0x8003A90C, raw)
    from_int = decode_jal(0x8003A90C, 0x0C00EC89)
    assert from_bytes == from_int


def test_decode_jal_bytes_rejects_wrong_length():
    with pytest.raises(ValueError):
        decode_jal_bytes(0x8003A90C, b"\x00\x00\x00")


def test_jal_decode_result_is_immutable_dataclass():
    result = decode_jal(0x8003A900, 0x0C00EBFF)
    assert isinstance(result, JalDecodeResult)
    with pytest.raises(AttributeError):
        result.target = 0  # frozen dataclass


# ---------------------------------------------------------------------------
# validate_call_site
# ---------------------------------------------------------------------------


def _fake_reader(memory: dict[int, bytes]):
    def read_memory(addr: int, length: int) -> bytes | None:
        data = memory.get(addr)
        if data is None or len(data) != length:
            return None
        return data

    return read_memory


def test_validate_call_site_succeeds_when_everything_matches():
    expectation = CallSiteExpectation(
        call_site_addr=0x8003A90C,
        expected_instruction=0x0C00EC89,
        expected_target=0x8003B224,
        expected_return_address=0x8003A914,
        profile_name="chapter1-test",
    )
    read_memory = _fake_reader({0x8003A90C: (0x0C00EC89).to_bytes(4, "little")})
    result = validate_call_site(expectation, read_memory)
    assert result.target == 0x8003B224


def test_validate_call_site_raises_on_read_failure():
    expectation = CallSiteExpectation(
        call_site_addr=0x8003A90C,
        expected_instruction=0x0C00EC89,
        expected_target=0x8003B224,
        expected_return_address=0x8003A914,
    )
    read_memory = _fake_reader({})  # nothing mapped
    with pytest.raises(CallSiteMismatchError):
        validate_call_site(expectation, read_memory)


def test_validate_call_site_raises_when_live_instruction_differs():
    # Simulates exactly the "code layout drifted" scenario this session
    # hit repeatedly: the byte content at a previously-known address has
    # changed to something else entirely.
    expectation = CallSiteExpectation(
        call_site_addr=0x8004A36C,
        expected_instruction=0x27BDFFD0,  # "shifted" layout prologue
        expected_target=0x8003B224,
        expected_return_address=0x8003A914,
        profile_name="shifted-layout",
    )
    read_memory = _fake_reader({0x8004A36C: (0x27BDFFE0).to_bytes(4, "little")})  # "original" layout instead
    with pytest.raises(CallSiteMismatchError, match="code layout likely drifted"):
        validate_call_site(expectation, read_memory)


def test_validate_call_site_raises_when_target_differs_even_if_instruction_matches():
    # Guards against a caller supplying an internally-inconsistent
    # expectation (expected_instruction decodes to a different target
    # than expected_target claims) rather than trusting the stale value.
    expectation = CallSiteExpectation(
        call_site_addr=0x8003A90C,
        expected_instruction=0x0C00EC89,
        expected_target=0x8003B1E4,  # the WRONG hand-computed value
        expected_return_address=0x8003A914,
    )
    read_memory = _fake_reader({0x8003A90C: (0x0C00EC89).to_bytes(4, "little")})
    with pytest.raises(CallSiteMismatchError):
        validate_call_site(expectation, read_memory)


def test_validate_call_site_raises_when_return_address_differs():
    expectation = CallSiteExpectation(
        call_site_addr=0x8003A90C,
        expected_instruction=0x0C00EC89,
        expected_target=0x8003B224,
        expected_return_address=0x8003A904,  # the WRONG pc+4 value
    )
    read_memory = _fake_reader({0x8003A90C: (0x0C00EC89).to_bytes(4, "little")})
    with pytest.raises(CallSiteMismatchError):
        validate_call_site(expectation, read_memory)
