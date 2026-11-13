"""The engine never sees who a person is: only numbers about their body and a room.

Client identity (name, contact, anything identifying) belongs in a separate client vault on the customer's
own machine, linked only by a random client code. See docs/privacy.md. This module rejects identifying
fields if they ever reach the engine's inputs.
"""

# Field names that identify a person or a home. Matched against column names and JSON keys, ignoring case,
# spaces, hyphens and underscores, as whole words: "client_name", "Date of Birth", "home address" all match.
IDENTIFYING = {
    "name", "firstname", "lastname", "fullname", "clientname", "patientname",
    "dob", "dateofbirth", "birthdate", "birthday", "age",
    "address", "street", "city", "zip", "zipcode", "postcode", "postalcode",
    "phone", "telephone", "mobile", "email", "fax",
    "ssn", "socialsecurity", "medicalrecord", "mrn", "insurance", "insuranceid", "accountnumber",
    "diagnosis",
}


class IdentifyingDataError(ValueError):
    """Identifying information reached the engine. The message says where."""


def _norm(key):
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


_SUFFIXES = ("name", "address", "phone", "email", "dob", "birthdate")


def _hit(key):
    k = _norm(key)
    return k in IDENTIFYING or k.endswith(_SUFFIXES)


def check_fields(keys, where):
    """Reject column names or keys that would identify a person or a home."""
    bad = sorted({str(k) for k in keys if k is not None and _hit(k)})
    if bad:
        raise IdentifyingDataError(
            f"{where}: {', '.join(bad)} would identify a person or a home. The engine only takes numbers and "
            "a client code; keep identity in the client vault on the customer's machine (docs/privacy.md).")


def check_tree(data, where):
    """Walk a JSON-like structure (a room, a profile) and reject identifying keys at any depth."""
    if isinstance(data, dict):
        check_fields(data.keys(), where)
        for k, v in data.items():
            check_tree(v, f"{where}.{k}")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            check_tree(v, f"{where}[{i}]")
