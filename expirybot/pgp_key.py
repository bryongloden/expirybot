import datetime
import re

import logging
LOG = logging.getLogger(__name__)


class OpenPGPVersion3FingerprintUnsupported(ValueError):
    pass


class PGPKey:
    EMAIL_PATTERN = '(?P<email>.+@.+\..+)'

    def __init__(self, fingerprint=None, algorithm_number=None, size_bits=None,
                 uids=None, expiry_date=None, created_date=None, **kwargs):
        self._fingerprint = None
        self._algorithm_number = None
        self._size_bits = None
        self._created_date = None
        self._expiry_date = None
        self._uids = []
        self._revoked = False

        if fingerprint is not None:
            self.set_fingerprint(fingerprint)

        if algorithm_number is not None:
            self.set_algorithm_number(algorithm_number)

        if size_bits is not None:
            self.set_size_bits(size_bits)

        if uids is not None:
            for uid in uids.split('|'):
                self.add_uid(uid)

        if created_date is not None:
            self.set_created_date(created_date)

        if expiry_date is not None:
            self.set_expiry_date(expiry_date)

    def __str__(self):
        return 'PGPKey({} {})'.format(
            self.fingerprint,
            '[revoked]' if self._revoked else '[expires {}]'.format(
                self.expiry_date)
        )

    def set_fingerprint(self, fingerprint):
        self._fingerprint = Fingerprint(fingerprint)

    def set_algorithm_number(self, algorithm_number):
        self._algorithm_number = int(algorithm_number)

    def set_size_bits(self, size_bits):
        if not isinstance(size_bits, int):
            size_bits = int(size_bits)

        self._size_bits = size_bits

    def set_created_timestamp(self, timestamp):
        self._created_date = self._parse_timestamp(timestamp)

    def set_expiry_timestamp(self, timestamp):
        self._expiry_date = self._parse_timestamp(timestamp)

    def set_created_date(self, date):
        self._created_date = self._parse_date(date)

    def set_expiry_date(self, date):
        self._expiry_date = self._parse_date(date)

    def add_uid(self, uid_string):
        assert isinstance(uid_string, str)
        if '\0' in uid_string:
            raise ValueError('NULL byte in uid for {}'.format(self))

        self._uids.append(uid_string)

    def set_revoked(self):
        self._revoked = True

    @property
    def fingerprint(self):
        return self._fingerprint

    @property
    def long_id(self):
        return self._fingerprint.to_long_id()

    @property
    def has_expired(self, today=None):
        if today is None:
            today = datetime.date.today()

        if self.expiry_date is None:
            return False
        else:
            return self.expiry_date < today

    @property
    def is_revoked(self):
        return self._revoked

    @property
    def is_valid(self):
        return self._fingerprint is not None and not self._revoked

    @property
    def days_until_expiry(self, today=None):
        if today is None:
            today = datetime.date.today()

        if self.expiry_date:
            return (self.expiry_date - today).days
        else:
            return None

    @property
    def friendly_expiry_date(self):
        if self.expiry_date:
            return self.expiry_date.strftime('%A %d %B %Y')
        else:
            return None

    @property
    def algorithm_number(self):
        return self._algorithm_number

    @property
    def size_bits(self):
        return self._size_bits

    @property
    def created_date(self):
        return self._created_date

    @property
    def expiry_date(self):
        return self._expiry_date

    @property
    def uids(self):
        return self._uids

    @property
    def primary_email(self):
        emails = self.emails

        if len(emails):
            return emails[0]

    @property
    def emails(self):
        return list(filter(None, map(self._parse_uid_as_email, self.uids)))

    @property
    def email_lines(self):

        return list(filter(
            None,
            map(self._parse_uid_as_email_line, self.uids)
        ))

    @staticmethod
    def _parse_uid_as_email(uid):
        patterns = [
            '.*<' + PGPKey.EMAIL_PATTERN + '>$',
            '^' + PGPKey.EMAIL_PATTERN + '$',
        ]
        for pattern in patterns:
            match = re.match(pattern, uid)

            if match:
                return match.group('email')

    @staticmethod
    def _parse_uid_as_email_line(uid):
        patterns = [
            r'^(?P<name>.*?) *\(.*\) *<' + PGPKey.EMAIL_PATTERN + '>$',
            r'^(?P<email>.+@.+\..+)$',  # paul@example.com
        ]

        for pattern in patterns:
            match = re.match(pattern, uid)

            if match is None:
                continue

            if match.groupdict().get('name', ''):
                return '{} <{}>'.format(
                    match.group('name'), match.group('email')
                )
            else:
                return match.group('email')

    def expires_in(self, days):
        return self.days_until_expiry == days

    @staticmethod
    def _parse_date(date):
        """
        Handle None, datetime.datetime(...) and 'YYYY-MM-DD'
        """
        if not date:
            return date

        elif isinstance(date, datetime.date):
            return date

        elif isinstance(date, str):
            return datetime.date(
                *[int(part) for part in date.split('-')]
            )

        else:
            raise TypeError('Unknown date format: {}'.format(date))

    @staticmethod
    def _parse_timestamp(timestamp):
        if not isinstance(timestamp, int):
            timestamp = int(timestamp)

        return datetime.datetime.fromtimestamp(timestamp).date()


class Fingerprint():
    def __init__(self, fingerprint_string):
        self._hex_digits = self.normalize(fingerprint_string)

    def normalize(self, string):
        pattern = r'^(0x)?(?P<hex>([A-Fa-f0-9]{4}\s*){10})$'
        match = re.match(pattern, string)

        if match is not None:
            return re.sub(
                '[^A-Fa-f0-9]',
                '',
                match.group('hex').upper()
            )  # e.g. return 'A999B749...'
        else:
            if len(string) == 16:
                LOG.debug("Dropping v3 key {}".format(string))
                raise OpenPGPVersion3FingerprintUnsupported(
                    '{}'.format(string)
                )
            else:
                raise ValueError(
                    "Fingerprint appears to be invalid: `{}`".format(string))

    def to_long_id(self):
        return '0x{}'.format(self._hex_digits.upper().replace(' ', '')[-16:])

    def __str__(self):
        return '{} {} {} {} {}  {} {} {} {} {}'.format(
            self._hex_digits[0:4],
            self._hex_digits[4:8],
            self._hex_digits[8:12],
            self._hex_digits[12:16],
            self._hex_digits[16:20],
            self._hex_digits[20:24],
            self._hex_digits[24:28],
            self._hex_digits[28:32],
            self._hex_digits[32:36],
            self._hex_digits[36:40]
        )

    def __repr__(self):
        return '<Fingerprint {}>'.format(self.__str__())

    def __eq__(self, other):
        if not isinstance(other, Fingerprint):
            other = Fingerprint(other)
        return self.hex_format == other.hex_format

    def __hash__(self):
        return hash(self._hex_digits)

    @property
    def hex_format(self):
        return '0x{}'.format(self._hex_digits)
