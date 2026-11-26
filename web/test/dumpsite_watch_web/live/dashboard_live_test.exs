defmodule DumpsiteWatchWeb.DashboardLiveTest do
  use DumpsiteWatchWeb.ConnCase

  test "GET /", %{conn: conn} do
    conn = get(conn, ~p"/")
    assert html_response(conn, 200) =~ "Pilot evidence workspace"
  end
end
