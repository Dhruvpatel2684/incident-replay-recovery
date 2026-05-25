"""
Validator Module
Performs certificate validity checks including expiration and key usage.
"""

from datetime import datetime


def parse_time(time_str):
    """Parse an ISO-8601 timestamp string to a datetime object."""
    # Handle Z suffix
    if time_str.endswith('Z'):
        time_str = time_str[:-1] + '+00:00'
    return datetime.fromisoformat(time_str)


def check_expiration(cert, reference_time_str):
    """
    Check whether a certificate is expired at the given reference time.
    Returns True if the certificate is still valid (not expired).
    """
    reference_time = parse_time(reference_time_str)
    not_after = parse_time(cert["not_after"])
    not_before = parse_time(cert["not_before"])

    # BUG: uses <= instead of <
    # When reference_time equals not_after exactly, cert should be expired
    # but this incorrectly treats it as valid
    if reference_time <= not_after and reference_time >= not_before:
        return True
    return False


def check_key_usage(cert, required_key_usage):
    """
    Check whether a certificate has the required key usage bits set.
    Only applies to non-CA leaf certificates.
    Returns True if key usage requirements are satisfied.
    """
    if cert.get("is_ca", False):
        # CA certs have their own key usage requirements
        return True

    cert_usage = cert.get("key_usage", 0)

    # BUG: uses bitwise OR and checks != 0 instead of bitwise AND == required
    # This means any overlap passes, even if not all required bits are set
    if cert_usage | required_key_usage != 0:
        return True
    return False


def validate_cert(cert, reference_time_str, required_leaf_key_usage):
    """
    Perform all validation checks on a single certificate.
    Returns a dict with validation results.
    """
    results = {
        "serial": cert["serial"],
        "subject_cn": cert["subject_cn"],
        "is_expired": not check_expiration(cert, reference_time_str),
        "key_usage_valid": check_key_usage(cert, required_leaf_key_usage),
    }
    return results
