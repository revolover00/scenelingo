import pytest

from preferences import LANGUAGE_CODES, validate_interval, validate_language


def test_supported_languages():
    assert len(LANGUAGE_CODES) == 10
    assert validate_language('en') == 'en'
    with pytest.raises(ValueError):
        validate_language('invalid')


@pytest.mark.parametrize('value,expected', [('30', 30), (' 60 ', 60), (180, 180), ('1440', 1440)])
def test_valid_intervals(value, expected):
    assert validate_interval(value) == expected


@pytest.mark.parametrize('value', ['4', '29', '1441', '-5', '1.5', '', '5 minutes'])
def test_invalid_interval_values_raise_value_error(value):
    with pytest.raises(ValueError):
        validate_interval(value)


@pytest.mark.parametrize('value', [True, 5.5, None])
def test_invalid_interval_types_raise_type_error(value):
    with pytest.raises(TypeError):
        validate_interval(value)
