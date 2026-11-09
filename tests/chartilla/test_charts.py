import datetime as dt

import allure
import pytest

from framework import endpoint
from services.object_manager.models import ChartData

SERVICE = "object-manager"
CHART = "/chartilla/public/v2/chart/{object_type}/{chart_type}"


def ts_filters(hours: int = 24) -> dict:
    end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return {"timestamp_start": (end - dt.timedelta(hours=hours)).isoformat(), "timestamp_end": end.isoformat()}


@allure.feature("chartilla")
@allure.story("chart v2")
class TestCharts:
    @pytest.mark.smoke
    @pytest.mark.parametrize("object_type", ["face", "vehicle", "person"])
    @pytest.mark.parametrize("chart_type", ["hist_chart", "line_chart", "numeric"])
    @endpoint(SERVICE, "POST", CHART)
    def test_chart_types(self, chartilla_api, object_type, chart_type):
        body = {"timestamp_filters": ts_filters(), "detalization": 3600}
        data = chartilla_api.chart(object_type, chart_type, body).assert_status(200).assert_contract().parse(ChartData)
        if chart_type == "numeric":
            assert isinstance(data.series, (int, float)), "numeric возвращает число в series"
        else:
            # сутки при detalization=3600 -> 24..25 часовых корзин (границы округляются до часа)
            assert 24 <= len(data.categories or []) <= 25

    @pytest.mark.parametrize(
        "object_type, group_by",
        [("face", "gender"), ("face", "age"), ("vehicle", "vehicle_type"), ("vehicle", "color"), ("person", "camera_id")],
    )
    @endpoint(SERVICE, "POST", CHART)
    def test_pie_chart_group_by(self, chartilla_api, object_type, group_by):
        body = {"timestamp_filters": ts_filters(), "group_by": group_by}
        data = chartilla_api.chart(object_type, "pie_chart", body).assert_status(200).parse(ChartData)
        assert data.series is not None

    @endpoint(SERVICE, "POST", CHART)
    def test_hist_chart_group_by_list(self, chartilla_api):
        body = {"timestamp_filters": ts_filters(), "detalization": 3600, "group_by": ["vehicle_type"]}
        data = chartilla_api.chart("vehicle", "hist_chart", body).assert_status(200).assert_contract().parse(ChartData)
        assert data.group_by == ["vehicle_type"]
        assert data.categories, "hist_chart должен возвращать categories (временные корзины)"

    @endpoint(SERVICE, "POST", CHART)
    def test_start_after_end(self, chartilla_api):
        f = ts_filters()
        body = {"timestamp_filters": {"timestamp_start": f["timestamp_end"], "timestamp_end": f["timestamp_start"]}, "detalization": 3600}
        chartilla_api.chart("face", "hist_chart", body).assert_error(400)

    @endpoint(SERVICE, "POST", CHART)
    def test_empty_timestamps(self, chartilla_api):
        chartilla_api.chart("face", "hist_chart", {"detalization": 3600}).assert_error(400)

    @endpoint(SERVICE, "POST", CHART)
    def test_detalization_greater_than_interval(self, chartilla_api):
        body = {"timestamp_filters": ts_filters(hours=1), "detalization": 86400}
        chartilla_api.chart("face", "hist_chart", body).assert_error(400)

    @endpoint(SERVICE, "POST", CHART)
    def test_numeric_with_group_by(self, chartilla_api):
        body = {"timestamp_filters": ts_filters(), "group_by": "gender"}
        chartilla_api.chart("face", "numeric", body).assert_error(400)

    @endpoint(SERVICE, "POST", CHART)
    def test_unknown_chart_type(self, chartilla_api):
        chartilla_api.chart("face", "radar_chart", {"timestamp_filters": ts_filters()}).assert_status(422)

    @endpoint(SERVICE, "POST", CHART)
    def test_unknown_group_by(self, chartilla_api):
        body = {"timestamp_filters": ts_filters(), "group_by": "shoe_size"}
        chartilla_api.chart("face", "pie_chart", body).assert_status(422)

    @endpoint(SERVICE, "POST", CHART)
    def test_unauthorized(self, anon_chartilla, bad_token):
        anon_chartilla.with_token(bad_token).chart("face", "numeric", {"timestamp_filters": ts_filters()}).assert_unauthorized()
