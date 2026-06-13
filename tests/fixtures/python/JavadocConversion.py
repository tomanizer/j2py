from __future__ import annotations


class JavadocConversion:
    """Normalizes input strings for review.

    References `normalize(String)` and `normalize(String, Object)` values.
    """

    def normalize(self, value: str) -> str:
        """Normalize the supplied value.

        Args:
            value: the raw value to normalize

        Returns:
            the normalized value

        Raises:
            IllegalArgumentException: when value is invalid
        """

        return value

    def clean(self, value: str) -> str:
        """Clean a value.

        .. deprecated:: use `normalize(String)` instead.

        Args:
            value: the raw value

        Returns:
            the cleaned value
        """

        return self.normalize(value)
