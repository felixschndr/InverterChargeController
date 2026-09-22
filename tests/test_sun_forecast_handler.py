import datetime
from datetime import time
from unittest.mock import Mock

import pytest

from source.energy_classes import EnergyAmount, Power, StateOfCharge
from source.sun_forecast_handler import SunForecastHandler


@pytest.fixture
def average_power_consumption_per_time_of_day() -> dict[time, Power]:
    return {
        time(hour=0, minute=00): Power(222),
        time(hour=0, minute=5): Power(225),
        time(hour=0, minute=10): Power(212),
        time(hour=0, minute=15): Power(228),
        time(hour=0, minute=20): Power(210),
        time(hour=0, minute=25): Power(221),
        time(hour=0, minute=30): Power(232),
        time(hour=0, minute=35): Power(229),
        time(hour=0, minute=40): Power(242),
        time(hour=0, minute=45): Power(218),
        time(hour=0, minute=50): Power(221),
        time(hour=0, minute=55): Power(221),
        time(hour=1, minute=00): Power(207),
        time(hour=1, minute=5): Power(215),
        time(hour=1, minute=10): Power(211),
        time(hour=1, minute=15): Power(206),
        time(hour=1, minute=20): Power(195),
        time(hour=1, minute=25): Power(188),
        time(hour=1, minute=30): Power(188),
        time(hour=1, minute=35): Power(180),
        time(hour=1, minute=40): Power(194),
        time(hour=1, minute=45): Power(187),
        time(hour=1, minute=50): Power(185),
        time(hour=1, minute=55): Power(197),
        time(hour=2, minute=00): Power(193),
        time(hour=2, minute=5): Power(205),
        time(hour=2, minute=10): Power(181),
        time(hour=2, minute=15): Power(178),
        time(hour=2, minute=20): Power(181),
        time(hour=2, minute=25): Power(175),
        time(hour=2, minute=30): Power(172),
        time(hour=2, minute=35): Power(190),
        time(hour=2, minute=40): Power(186),
        time(hour=2, minute=45): Power(170),
        time(hour=2, minute=50): Power(174),
        time(hour=2, minute=55): Power(167),
        time(hour=3, minute=00): Power(172),
        time(hour=3, minute=5): Power(173),
        time(hour=3, minute=10): Power(176),
        time(hour=3, minute=15): Power(171),
        time(hour=3, minute=20): Power(170),
        time(hour=3, minute=25): Power(201),
        time(hour=3, minute=30): Power(221),
        time(hour=3, minute=35): Power(233),
        time(hour=3, minute=40): Power(247),
        time(hour=3, minute=45): Power(255),
        time(hour=3, minute=50): Power(244),
        time(hour=3, minute=55): Power(231),
        time(hour=4, minute=00): Power(241),
        time(hour=4, minute=5): Power(240),
        time(hour=4, minute=10): Power(237),
        time(hour=4, minute=15): Power(232),
        time(hour=4, minute=20): Power(237),
        time(hour=4, minute=25): Power(235),
        time(hour=4, minute=30): Power(245),
        time(hour=4, minute=35): Power(233),
        time(hour=4, minute=40): Power(228),
        time(hour=4, minute=45): Power(240),
        time(hour=4, minute=50): Power(236),
        time(hour=4, minute=55): Power(246),
        time(hour=5, minute=00): Power(240),
        time(hour=5, minute=5): Power(235),
        time(hour=5, minute=10): Power(253),
        time(hour=5, minute=15): Power(239),
        time(hour=5, minute=20): Power(239),
        time(hour=5, minute=25): Power(243),
        time(hour=5, minute=30): Power(239),
        time(hour=5, minute=35): Power(241),
        time(hour=5, minute=40): Power(245),
        time(hour=5, minute=45): Power(239),
        time(hour=5, minute=50): Power(246),
        time(hour=5, minute=55): Power(254),
        time(hour=6, minute=00): Power(234),
        time(hour=6, minute=5): Power(264),
        time(hour=6, minute=10): Power(244),
        time(hour=6, minute=15): Power(266),
        time(hour=6, minute=20): Power(268),
        time(hour=6, minute=25): Power(279),
        time(hour=6, minute=30): Power(296),
        time(hour=6, minute=35): Power(313),
        time(hour=6, minute=40): Power(308),
        time(hour=6, minute=45): Power(301),
        time(hour=6, minute=50): Power(314),
        time(hour=6, minute=55): Power(443),
        time(hour=7, minute=00): Power(585),
        time(hour=7, minute=5): Power(603),
        time(hour=7, minute=10): Power(616),
        time(hour=7, minute=15): Power(620),
        time(hour=7, minute=20): Power(625),
        time(hour=7, minute=25): Power(604),
        time(hour=7, minute=30): Power(608),
        time(hour=7, minute=35): Power(648),
        time(hour=7, minute=40): Power(633),
        time(hour=7, minute=45): Power(612),
        time(hour=7, minute=50): Power(670),
        time(hour=7, minute=55): Power(628),
        time(hour=8, minute=00): Power(651),
        time(hour=8, minute=5): Power(666),
        time(hour=8, minute=10): Power(649),
        time(hour=8, minute=15): Power(642),
        time(hour=8, minute=20): Power(625),
        time(hour=8, minute=25): Power(593),
        time(hour=8, minute=30): Power(591),
        time(hour=8, minute=35): Power(584),
        time(hour=8, minute=40): Power(613),
        time(hour=8, minute=45): Power(583),
        time(hour=8, minute=50): Power(563),
        time(hour=8, minute=55): Power(617),
        time(hour=9, minute=00): Power(575),
        time(hour=9, minute=5): Power(601),
        time(hour=9, minute=10): Power(599),
        time(hour=9, minute=15): Power(598),
        time(hour=9, minute=20): Power(579),
        time(hour=9, minute=25): Power(577),
        time(hour=9, minute=30): Power(604),
        time(hour=9, minute=35): Power(549),
        time(hour=9, minute=40): Power(590),
        time(hour=9, minute=45): Power(533),
        time(hour=9, minute=50): Power(508),
        time(hour=9, minute=55): Power(492),
        time(hour=10, minute=00): Power(523),
        time(hour=10, minute=5): Power(447),
        time(hour=10, minute=10): Power(413),
        time(hour=10, minute=15): Power(394),
        time(hour=10, minute=20): Power(403),
        time(hour=10, minute=25): Power(346),
        time(hour=10, minute=30): Power(389),
        time(hour=10, minute=35): Power(338),
        time(hour=10, minute=40): Power(323),
        time(hour=10, minute=45): Power(257),
        time(hour=10, minute=50): Power(259),
        time(hour=10, minute=55): Power(223),
        time(hour=11, minute=00): Power(218),
        time(hour=11, minute=5): Power(250),
        time(hour=11, minute=10): Power(189),
        time(hour=11, minute=15): Power(191),
        time(hour=11, minute=20): Power(205),
        time(hour=11, minute=25): Power(227),
        time(hour=11, minute=30): Power(207),
        time(hour=11, minute=35): Power(222),
        time(hour=11, minute=40): Power(208),
        time(hour=11, minute=45): Power(195),
        time(hour=11, minute=50): Power(210),
        time(hour=11, minute=55): Power(209),
        time(hour=12, minute=00): Power(193),
        time(hour=12, minute=5): Power(180),
        time(hour=12, minute=10): Power(149),
        time(hour=12, minute=15): Power(159),
        time(hour=12, minute=20): Power(162),
        time(hour=12, minute=25): Power(166),
        time(hour=12, minute=30): Power(169),
        time(hour=12, minute=35): Power(196),
        time(hour=12, minute=40): Power(209),
        time(hour=12, minute=45): Power(214),
        time(hour=12, minute=50): Power(221),
        time(hour=12, minute=55): Power(218),
        time(hour=13, minute=00): Power(211),
        time(hour=13, minute=5): Power(197),
        time(hour=13, minute=10): Power(208),
        time(hour=13, minute=15): Power(179),
        time(hour=13, minute=20): Power(199),
        time(hour=13, minute=25): Power(206),
        time(hour=13, minute=30): Power(185),
        time(hour=13, minute=35): Power(169),
        time(hour=13, minute=40): Power(170),
        time(hour=13, minute=45): Power(169),
        time(hour=13, minute=50): Power(156),
        time(hour=13, minute=55): Power(172),
        time(hour=14, minute=00): Power(168),
        time(hour=14, minute=5): Power(161),
        time(hour=14, minute=10): Power(182),
        time(hour=14, minute=15): Power(195),
        time(hour=14, minute=20): Power(182),
        time(hour=14, minute=25): Power(192),
        time(hour=14, minute=30): Power(198),
        time(hour=14, minute=35): Power(176),
        time(hour=14, minute=40): Power(212),
        time(hour=14, minute=45): Power(181),
        time(hour=14, minute=50): Power(199),
        time(hour=14, minute=55): Power(237),
        time(hour=15, minute=00): Power(219),
        time(hour=15, minute=5): Power(205),
        time(hour=15, minute=10): Power(220),
        time(hour=15, minute=15): Power(222),
        time(hour=15, minute=20): Power(257),
        time(hour=15, minute=25): Power(275),
        time(hour=15, minute=30): Power(287),
        time(hour=15, minute=35): Power(309),
        time(hour=15, minute=40): Power(261),
        time(hour=15, minute=45): Power(243),
        time(hour=15, minute=50): Power(274),
        time(hour=15, minute=55): Power(254),
        time(hour=16, minute=00): Power(289),
        time(hour=16, minute=5): Power(300),
        time(hour=16, minute=10): Power(314),
        time(hour=16, minute=15): Power(289),
        time(hour=16, minute=20): Power(299),
        time(hour=16, minute=25): Power(283),
        time(hour=16, minute=30): Power(310),
        time(hour=16, minute=35): Power(324),
        time(hour=16, minute=40): Power(358),
        time(hour=16, minute=45): Power(384),
        time(hour=16, minute=50): Power(412),
        time(hour=16, minute=55): Power(493),
        time(hour=17, minute=00): Power(456),
        time(hour=17, minute=5): Power(454),
        time(hour=17, minute=10): Power(484),
        time(hour=17, minute=15): Power(484),
        time(hour=17, minute=20): Power(493),
        time(hour=17, minute=25): Power(545),
        time(hour=17, minute=30): Power(550),
        time(hour=17, minute=35): Power(593),
        time(hour=17, minute=40): Power(663),
        time(hour=17, minute=45): Power(649),
        time(hour=17, minute=50): Power(644),
        time(hour=17, minute=55): Power(632),
        time(hour=18, minute=00): Power(583),
        time(hour=18, minute=5): Power(545),
        time(hour=18, minute=10): Power(605),
        time(hour=18, minute=15): Power(551),
        time(hour=18, minute=20): Power(563),
        time(hour=18, minute=25): Power(575),
        time(hour=18, minute=30): Power(515),
        time(hour=18, minute=35): Power(520),
        time(hour=18, minute=40): Power(524),
        time(hour=18, minute=45): Power(489),
        time(hour=18, minute=50): Power(440),
        time(hour=18, minute=55): Power(436),
        time(hour=19, minute=00): Power(435),
        time(hour=19, minute=5): Power(448),
        time(hour=19, minute=10): Power(434),
        time(hour=19, minute=15): Power(429),
        time(hour=19, minute=20): Power(435),
        time(hour=19, minute=25): Power(416),
        time(hour=19, minute=30): Power(405),
        time(hour=19, minute=35): Power(378),
        time(hour=19, minute=40): Power(343),
        time(hour=19, minute=45): Power(362),
        time(hour=19, minute=50): Power(348),
        time(hour=19, minute=55): Power(404),
        time(hour=20, minute=00): Power(404),
        time(hour=20, minute=5): Power(395),
        time(hour=20, minute=10): Power(395),
        time(hour=20, minute=15): Power(390),
        time(hour=20, minute=20): Power(368),
        time(hour=20, minute=25): Power(340),
        time(hour=20, minute=30): Power(327),
        time(hour=20, minute=35): Power(325),
        time(hour=20, minute=40): Power(308),
        time(hour=20, minute=45): Power(334),
        time(hour=20, minute=50): Power(321),
        time(hour=20, minute=55): Power(299),
        time(hour=21, minute=00): Power(333),
        time(hour=21, minute=5): Power(304),
        time(hour=21, minute=10): Power(337),
        time(hour=21, minute=15): Power(313),
        time(hour=21, minute=20): Power(318),
        time(hour=21, minute=25): Power(298),
        time(hour=21, minute=30): Power(301),
        time(hour=21, minute=35): Power(320),
        time(hour=21, minute=40): Power(367),
        time(hour=21, minute=45): Power(333),
        time(hour=21, minute=50): Power(344),
        time(hour=21, minute=55): Power(307),
        time(hour=22, minute=00): Power(326),
        time(hour=22, minute=5): Power(309),
        time(hour=22, minute=10): Power(292),
        time(hour=22, minute=15): Power(288),
        time(hour=22, minute=20): Power(307),
        time(hour=22, minute=25): Power(284),
        time(hour=22, minute=30): Power(303),
        time(hour=22, minute=35): Power(315),
        time(hour=22, minute=40): Power(283),
        time(hour=22, minute=45): Power(289),
        time(hour=22, minute=50): Power(281),
        time(hour=22, minute=55): Power(292),
        time(hour=23, minute=00): Power(257),
        time(hour=23, minute=5): Power(260),
        time(hour=23, minute=10): Power(284),
        time(hour=23, minute=15): Power(263),
        time(hour=23, minute=20): Power(256),
        time(hour=23, minute=25): Power(237),
        time(hour=23, minute=30): Power(242),
        time(hour=23, minute=35): Power(220),
        time(hour=23, minute=40): Power(249),
        time(hour=23, minute=45): Power(244),
        time(hour=23, minute=50): Power(219),
        time(hour=23, minute=55): Power(243),
    }


@pytest.mark.parametrize(
    "starting_time",
    [time(hour=0, minute=0), time(hour=0, minute=5), time(hour=11, minute=55), time(hour=23, minute=40)],
)
def test_calculate_energy_usage_in_timeframe(average_power_consumption_per_time_of_day, starting_time):
    timeframe_duration = datetime.timedelta(minutes=30)
    timeslot = int((timeframe_duration / 6).total_seconds())

    timeframe_start = datetime.datetime.combine(datetime.date(day=1, month=1, year=2020), starting_time)

    expected_relevant_power_consumptions = [
        average_power_consumption_per_time_of_day[(timeframe_start + datetime.timedelta(seconds=timeslot * i)).time()]
        for i in range(6)
    ]
    expected_average_power_consumption = sum(expected_relevant_power_consumptions) / len(
        expected_relevant_power_consumptions
    )
    expected_energy_usage = EnergyAmount.from_watt_seconds(
        expected_average_power_consumption.watts * timeframe_duration.total_seconds()
    )

    assert expected_energy_usage == SunForecastHandler._calculate_energy_usage_in_timeframe(
        Mock(), timeframe_start, timeframe_duration, average_power_consumption_per_time_of_day
    )


def test_make_debug_api_request():
    sun_forecast_handler = SunForecastHandler()

    data = sun_forecast_handler.retrieve_solar_data_from_api(retrieve_future_data=True)
    print(data)


@pytest.fixture
def read_charge_and_discharge_efficiency(isolated_environment_variables: pytest.MonkeyPatch):
    def read_efficiency(configured_percentage: str | None) -> float:
        if configured_percentage is None:
            isolated_environment_variables.delenv("INVERTER_CHARGE_DISCHARGE_EFFICIENCY", raising=False)
        else:
            isolated_environment_variables.setenv("INVERTER_CHARGE_DISCHARGE_EFFICIENCY", configured_percentage)
        return SunForecastHandler._get_charge_and_discharge_efficiency(Mock())

    return read_efficiency


@pytest.mark.parametrize(
    "configured_percentage, expected_factor",
    [("90", 0.9), ("100", 1.0), ("50.5", 0.505), ("1", 0.01)],
)
def test_charge_and_discharge_efficiency_is_converted_from_percent_to_a_factor(
    read_charge_and_discharge_efficiency, configured_percentage, expected_factor
):
    assert read_charge_and_discharge_efficiency(configured_percentage) == pytest.approx(expected_factor)


def test_charge_and_discharge_efficiency_falls_back_to_ninety_percent(read_charge_and_discharge_efficiency):
    assert read_charge_and_discharge_efficiency(None) == pytest.approx(0.9)


@pytest.mark.parametrize("configured_percentage", ["101", "5000", "0", "-1"])
def test_charge_and_discharge_efficiency_rejects_a_percentage_outside_of_the_valid_range(
    read_charge_and_discharge_efficiency, configured_percentage
):
    with pytest.raises(ValueError):
        read_charge_and_discharge_efficiency(configured_percentage)


def test_calculate_energy_usage_in_timeframe_rejects_consumption_data_without_any_entry():
    with pytest.raises(ValueError):
        SunForecastHandler._calculate_energy_usage_in_timeframe(
            Mock(), datetime.datetime(2020, 1, 1, 0, 0), datetime.timedelta(minutes=30), {}
        )


def test_calculate_energy_usage_in_timeframe_substitutes_the_overall_average_for_missing_times_of_day(
    average_power_consumption_per_time_of_day,
):
    timeframe_start = datetime.datetime(2020, 1, 1, 0, 0)
    timeframe_duration = datetime.timedelta(minutes=30)
    consumption_data_with_a_gap = {
        time_of_day: power
        for time_of_day, power in average_power_consumption_per_time_of_day.items()
        if time_of_day != time(hour=0, minute=15)
    }
    overall_average = sum(consumption_data_with_a_gap.values()) / len(consumption_data_with_a_gap)
    handler_stub = Mock()

    expected_average = (
        sum(
            [average_power_consumption_per_time_of_day[time(hour=0, minute=minute)] for minute in [0, 5, 10, 20, 25]],
            overall_average,
        )
        / 6
    )
    expected_energy_usage = EnergyAmount.from_watt_seconds(expected_average.watts * timeframe_duration.total_seconds())

    energy_usage = SunForecastHandler._calculate_energy_usage_in_timeframe(
        handler_stub, timeframe_start, timeframe_duration, consumption_data_with_a_gap
    )

    assert energy_usage.watt_hours == pytest.approx(expected_energy_usage.watt_hours)
    handler_stub.log.warning.assert_called_once()


@pytest.fixture
def sun_forecast_handler() -> SunForecastHandler:
    return SunForecastHandler()


def test_calculate_min_and_max_of_soc_in_timeframe_does_not_need_solar_data_to_be_retrieved_first(
    sun_forecast_handler, average_power_consumption_per_time_of_day
):
    timeframe_start = datetime.datetime(2020, 1, 1, 0, 0)
    period_duration = datetime.timedelta(minutes=30)
    timeframe_end = timeframe_start + datetime.timedelta(hours=2)
    solar_data_without_any_sun = {
        (timeframe_start + period_duration * index).isoformat(): Power(0) for index in range(1, 6)
    }
    starting_soc = StateOfCharge.from_percentage(50)

    minimum_soc, maximum_soc = sun_forecast_handler.calculate_min_and_max_of_soc_in_timeframe(
        timeframe_start,
        timeframe_end,
        average_power_consumption_per_time_of_day,
        starting_soc,
        False,
        solar_data_without_any_sun,
        period_duration,
    )

    assert maximum_soc == starting_soc
    assert minimum_soc < starting_soc


def test_get_debug_solar_data_returns_a_period_duration_that_matches_its_timestamps(sun_forecast_handler):
    solar_data, period_duration = sun_forecast_handler._get_debug_solar_data()

    timestamps = sorted(datetime.datetime.fromisoformat(timestamp) for timestamp in solar_data)
    assert period_duration == datetime.timedelta(minutes=30)
    assert timestamps[1] - timestamps[0] == period_duration
