defmodule DumpsiteWatchWeb.DashboardLive do
  use DumpsiteWatchWeb, :live_view

  alias DumpsiteWatchWeb.Layouts

  @filters %{
    "all" => "All leads",
    "dump_site_reported" => "Dumpsite mentioned",
    "river_dumping_reported" => "River dumping mentioned"
  }

  @impl true
  def mount(_params, _session, socket) do
    data = load_pilot_data!()
    first_lead = List.first(data["leads"])

    {:ok,
     socket
     |> assign(:page_title, "Nairobi pilot overview")
     |> assign(:county, data["county"])
     |> assign(:boundary_source, data["boundary_source"])
     |> assign(:boundary_path, data["boundary_path"])
     |> assign(:leads, data["leads"])
     |> assign(:lead_count, data["lead_count"])
     |> assign(:outside_point_count, data["outside_point_count"])
     |> assign(:filter_options, @filters)
     |> assign(:filter, "all")
     |> assign(:query, "")
     |> assign(:search_form, to_form(%{"query" => ""}, as: :search))
     |> assign(:selected_id, first_lead && first_lead["id"])
     |> assign(:filtered_leads, data["leads"])
     |> assign(:selected_lead, first_lead)}
  end

  @impl true
  def handle_event("search", %{"search" => %{"query" => query}}, socket) do
    {:noreply, apply_filters(socket, query, socket.assigns.filter)}
  end

  def handle_event("search", %{"query" => query}, socket) do
    {:noreply, apply_filters(socket, query, socket.assigns.filter)}
  end

  def handle_event("filter", %{"filter" => filter}, socket) do
    filter = if Map.has_key?(@filters, filter), do: filter, else: "all"
    {:noreply, apply_filters(socket, socket.assigns.query, filter)}
  end

  def handle_event("select_lead", %{"id" => id}, socket) do
    case Enum.find(socket.assigns.leads, &(&1["id"] == id)) do
      nil -> {:noreply, socket}
      lead -> {:noreply, assign(socket, selected_id: id, selected_lead: lead)}
    end
  end

  def handle_event("clear_search", _params, socket) do
    {:noreply, apply_filters(socket, "", socket.assigns.filter)}
  end

  defp apply_filters(socket, query, filter) do
    normalized_query = String.trim(query) |> String.downcase()

    visible =
      Enum.filter(socket.assigns.leads, fn lead ->
        matches_filter? = filter == "all" or lead["evidence_type"] == filter
        searchable = String.downcase(lead["name"] <> " " <> lead["evidence_notes"])
        matches_query? = normalized_query == "" or String.contains?(searchable, normalized_query)
        matches_filter? and matches_query?
      end)

    selected =
      Enum.find(visible, &(&1["id"] == socket.assigns.selected_id)) || List.first(visible)

    socket
    |> assign(:filter, filter)
    |> assign(:query, query)
    |> assign(:search_form, to_form(%{"query" => query}, as: :search))
    |> assign(:filtered_leads, visible)
    |> assign(:selected_id, selected && selected["id"])
    |> assign(:selected_lead, selected)
  end

  defp load_pilot_data! do
    :dumpsite_watch
    |> :code.priv_dir()
    |> to_string()
    |> Path.join("pilot_data.json")
    |> File.read!()
    |> Jason.decode!()
  end
end
