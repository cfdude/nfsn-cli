import hashlib

from nfsn_cli.auth import SALT_ALPHABET, SALT_LENGTH, auth_header, make_salt


def test_auth_header_matches_the_documented_scheme():
    login, api_key = "testuser", "topsecret"
    uri, body = "/dns/example.com/listRRs", ""
    body_hash = hashlib.sha1(body.encode()).hexdigest()
    expected_digest = hashlib.sha1(
        f"{login};1700000000;abc123;{api_key};{uri};{body_hash}".encode()
    ).hexdigest()

    header = auth_header(login, api_key, uri, body, timestamp=1700000000, salt="abc123")

    assert header == f"{login};1700000000;abc123;{expected_digest}"


def test_auth_header_has_four_semicolon_separated_fields():
    header = auth_header("user", "key", "/dns/example.com/addRR", "name=www&type=A")
    fields = header.split(";")
    assert len(fields) == 4
    assert fields[0] == "user"
    assert fields[1].isdigit()
    assert len(fields[2]) == SALT_LENGTH
    assert len(fields[3]) == 40


def test_body_is_part_of_the_signature():
    kwargs = {"timestamp": 1700000000, "salt": "abc123"}
    with_body = auth_header("u", "k", "/dns/example.com/addRR", "name=www", **kwargs)
    without_body = auth_header("u", "k", "/dns/example.com/addRR", "", **kwargs)
    assert with_body != without_body


def test_request_uri_is_part_of_the_signature():
    kwargs = {"timestamp": 1700000000, "salt": "abc123"}
    one = auth_header("u", "k", "/dns/example.com/addRR", "", **kwargs)
    two = auth_header("u", "k", "/dns/example.com/removeRR", "", **kwargs)
    assert one != two


def test_salt_is_random_and_within_the_alphabet():
    salts = {make_salt() for _ in range(50)}
    assert len(salts) == 50
    assert all(len(s) == SALT_LENGTH for s in salts)
    assert all(set(s) <= set(SALT_ALPHABET) for s in salts)
