defmodule DumpsiteWatch.Sites do
  @moduledoc "Data access for monitored dumpsite locations and their evidence."

  import Ecto.Query
  alias DumpsiteWatch.Repo
  alias DumpsiteWatch.RiskScore
  alias DumpsiteWatch.Sites.Site

  def list_ranked_sites(opts \\ []) do
    limit = Keyword.get(opts, :limit, 10)

    Site
    |> where([site], site.status in [:candidate, :under_review, :verified])
    |> order_by([site], desc_nulls_last: site.risk_score, asc: site.name)
    |> limit(^limit)
    |> Repo.all()
  end

  def change_site(%Site{} = site, attrs \\ %{}), do: Site.changeset(site, attrs)

  def create_site(attrs) do
    %Site{}
    |> Site.changeset(attrs)
    |> Repo.insert()
  end

  def recalculate_score(%Site{} = site) do
    with {:ok, result} <- RiskScore.calculate(site.risk_inputs) do
      site
      |> Site.changeset(%{
        risk_score: result.score,
        risk_factors: result.factors,
        score_version: result.version
      })
      |> Repo.update()
    end
  end
end
