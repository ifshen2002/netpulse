from services.auth import hash_password, verify_password


def test_scrypt_password_hash_round_trip():
    encoded = hash_password("a-long-enough-password")

    assert encoded.startswith("scrypt$")
    assert verify_password("a-long-enough-password", encoded)


def test_scrypt_password_hash_rejects_wrong_password_and_malformed_hash():
    encoded = hash_password("a-long-enough-password")

    assert not verify_password("wrong-password", encoded)
    assert not verify_password("a-long-enough-password", "not-a-valid-hash")
