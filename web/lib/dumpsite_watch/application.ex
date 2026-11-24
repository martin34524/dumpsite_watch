defmodule DumpsiteWatch.Application do
  # See https://elixir.hexdocs.pm/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      DumpsiteWatchWeb.Telemetry,
      DumpsiteWatch.Repo,
      {DNSCluster, query: Application.get_env(:dumpsite_watch, :dns_cluster_query) || :ignore},
      {Phoenix.PubSub, name: DumpsiteWatch.PubSub},
      # Start a worker by calling: DumpsiteWatch.Worker.start_link(arg)
      # {DumpsiteWatch.Worker, arg},
      # Start to serve requests, typically the last entry
      DumpsiteWatchWeb.Endpoint
    ]

    # See https://elixir.hexdocs.pm/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: DumpsiteWatch.Supervisor]
    Supervisor.start_link(children, opts)
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    DumpsiteWatchWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
