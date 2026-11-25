defmodule DumpsiteWatch.RiskScore do
  @moduledoc """
  Produces a transparent 0–100 priority score from normalized, non-negative factors.

  Inputs are values between 0 and 1. A value of 1 means greater concern. Missing
  inputs are omitted and the remaining weights are renormalized, so missing data
  is never silently treated as evidence of low risk.

  Equal weights are a provisional starting point only. They must be reviewed
  against pilot-county evidence before scores are used operationally.
  """

  @version "0.1-provisional"
  @weights %{
    size: 0.25,
    growth: 0.25,
    water_proximity: 0.25,
    people_proximity: 0.25
  }

  @type factor :: :size | :growth | :water_proximity | :people_proximity

  @spec calculate(map()) ::
          {:ok, map()} | {:error, :no_valid_factors | {:invalid_factors, [factor()]}}
  def calculate(factors) when is_map(factors) do
    factors = normalize_keys(factors)

    invalid =
      factors
      |> Enum.filter(fn {key, value} ->
        Map.has_key?(@weights, key) and not valid_factor?(value)
      end)
      |> Enum.map(&elem(&1, 0))

    supplied = Map.take(factors, Map.keys(@weights))

    cond do
      invalid != [] ->
        {:error, {:invalid_factors, invalid}}

      map_size(supplied) == 0 ->
        {:error, :no_valid_factors}

      true ->
        total_weight =
          Enum.reduce(supplied, 0.0, fn {key, _value}, total -> total + @weights[key] end)

        details =
          Map.new(supplied, fn {key, value} ->
            weight = @weights[key] / total_weight
            {key, %{value: value, weight: weight, contribution: value * weight}}
          end)

        score =
          details
          |> Map.values()
          |> Enum.reduce(0.0, fn detail, total -> total + detail.contribution end)
          |> Kernel.*(100)
          |> Float.round(1)

        {:ok, %{score: score, factors: details, version: @version}}
    end
  end

  def calculate(_factors), do: {:error, :no_valid_factors}

  defp normalize_keys(factors) do
    Map.new(@weights, fn {key, _weight} ->
      {key, Map.get(factors, key, Map.get(factors, Atom.to_string(key)))}
    end)
    |> Enum.reject(fn {_key, value} -> is_nil(value) end)
    |> Map.new()
  end

  defp valid_factor?(value), do: is_number(value) and value >= 0 and value <= 1
end
