defmodule DumpsiteWatchWeb.PageController do
  use DumpsiteWatchWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
