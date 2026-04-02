import json
import re


class CredentialParser:
    """Parse credential payloads copied from external developer portals."""

    _KEY_VALUE_PATTERNS = [
        re.compile(r'^\s*([A-Za-z0-9_\-.]+)\s*=\s*(.+?)\s*$'),
        re.compile(r'^\s*([A-Za-z0-9_\-.]+)\s*:\s*(.+?)\s*$'),
    ]

    @classmethod
    def parse(cls, raw_payload):
        """Return parsed key/value pairs from JSON or line-based payloads."""
        payload = (raw_payload or '').strip()
        if not payload:
            return {}

        parsed = cls._parse_json(payload)
        if parsed:
            return parsed

        return cls._parse_line_pairs(payload)

    @classmethod
    def _parse_json(cls, payload):
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError:
            return {}

        if not isinstance(loaded, dict):
            return {}

        return {str(key).strip(): str(value).strip() for key, value in loaded.items() if value is not None}

    @classmethod
    def _parse_line_pairs(cls, payload):
        pairs = {}
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            for pattern in cls._KEY_VALUE_PATTERNS:
                match = pattern.match(line)
                if match:
                    key, value = match.groups()
                    pairs[key.strip()] = value.strip().strip('"').strip("'")
                    break
        return pairs

    @classmethod
    def build_preview(cls, parsed_values, provider):
        aliases = cls._provider_aliases(provider)
        lines = []
        for source_key, value in parsed_values.items():
            alias_key = source_key.lower().replace('-', '_').replace('.', '_')
            target_field = aliases.get(alias_key, False)
            if source_key.lower() in aliases:
                confidence = 'high'
                note = 'Exact key matched'
            elif target_field:
                confidence = 'medium'
                note = f'Alias matched ({source_key} → {target_field})'
            else:
                confidence = 'low'
                note = 'Unrecognized key, map manually or ignore'
            lines.append(
                {
                    'source_key': source_key,
                    'target_field': target_field or '',
                    'detected_value': value,
                    'confidence': confidence,
                    'note': note,
                    'apply': bool(target_field),
                }
            )
        return lines

    @classmethod
    def _provider_aliases(cls, provider):
        if provider == 'meta':
            return {
                'app_id': 'app_id',
                'facebook_app_id': 'app_id',
                'fb_app_id': 'app_id',
                'app_secret': 'app_secret',
                'facebook_app_secret': 'app_secret',
                'meta_app_secret': 'app_secret',
                'client_id': 'client_id',
                'client_secret': 'client_secret',
                'access_token': 'access_token',
                'token': 'access_token',
                'long_lived_token': 'access_token',
                'refresh_token': 'refresh_token',
                'business_id': 'business_id',
                'ad_account_id': 'ad_account_id',
                'pixel_id': 'pixel_id',
                'scope': 'scope',
                'scopes': 'scope',
            }

        if provider == 'tiktok':
            return {
                'client_id': 'client_id',
                'client_key': 'client_id',
                'client_secret': 'client_secret',
                'app_secret': 'client_secret',
                'access_token': 'access_token',
                'refresh_token': 'refresh_token',
                'open_id': 'external_account_id',
                'external_account_id': 'external_account_id',
                'scope': 'scope',
                'scopes': 'scope',
            }

        return {}
