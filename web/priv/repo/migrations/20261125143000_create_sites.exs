defmodule DumpsiteWatch.Repo.Migrations.CreateSites do
  use Ecto.Migration

  def change do
    create table(:sites) do
      add :name, :string, null: false
      add :status, :string, null: false, default: "candidate"
      add :location, :geometry
      add :area_m2, :float
      add :growth_pct, :float
      add :distance_to_water_m, :float
      add :people_within_500m, :integer
      add :risk_score, :float
      add :risk_inputs, :map, null: false, default: %{}
      add :risk_factors, :map, null: false, default: %{}
      add :score_version, :string
      add :source_name, :string, null: false
      add :source_url, :text
      add :observed_on, :date
      add :evidence_notes, :text

      timestamps(type: :utc_datetime_usec)
    end

    create constraint(:sites, :sites_status_check,
             check: "status IN ('candidate', 'under_review', 'verified', 'rejected')"
           )

    create constraint(:sites, :sites_risk_score_range,
             check: "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)"
           )

    create index(:sites, [:status])
    create index(:sites, [:risk_score])
    execute("CREATE INDEX sites_location_gist_index ON sites USING GIST (location)")
  end
end
