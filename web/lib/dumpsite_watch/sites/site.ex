defmodule DumpsiteWatch.Sites.Site do
  use Ecto.Schema
  import Ecto.Changeset

  @statuses [:candidate, :under_review, :verified, :rejected]

  schema "sites" do
    field :name, :string
    field :status, Ecto.Enum, values: @statuses, default: :candidate
    field :location, Geo.PostGIS.Geometry
    field :area_m2, :float
    field :growth_pct, :float
    field :distance_to_water_m, :float
    field :people_within_500m, :integer
    field :risk_score, :float
    field :risk_inputs, :map, default: %{}
    field :risk_factors, :map, default: %{}
    field :score_version, :string
    field :source_name, :string
    field :source_url, :string
    field :observed_on, :date
    field :evidence_notes, :string

    timestamps(type: :utc_datetime_usec)
  end

  def changeset(site, attrs) do
    site
    |> cast(attrs, [
      :name,
      :status,
      :location,
      :area_m2,
      :growth_pct,
      :distance_to_water_m,
      :people_within_500m,
      :risk_score,
      :risk_inputs,
      :risk_factors,
      :score_version,
      :source_name,
      :source_url,
      :observed_on,
      :evidence_notes
    ])
    |> validate_required([:name, :status, :source_name])
    |> validate_number(:area_m2, greater_than_or_equal_to: 0)
    |> validate_number(:distance_to_water_m, greater_than_or_equal_to: 0)
    |> validate_number(:people_within_500m, greater_than_or_equal_to: 0)
    |> validate_number(:risk_score, greater_than_or_equal_to: 0, less_than_or_equal_to: 100)
  end
end
