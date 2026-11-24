defmodule DumpsiteWatch.Repo do
  use Ecto.Repo,
    otp_app: :dumpsite_watch,
    adapter: Ecto.Adapters.Postgres
end
