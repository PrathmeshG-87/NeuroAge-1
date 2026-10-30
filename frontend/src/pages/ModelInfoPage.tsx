import React, { useEffect, useState } from 'react'
import { Card } from '@/components/ui/Card'
import { KPICard } from '@/components/data-display/KPICard'
import { MedicalDisclaimer } from '@/components/assessment/MedicalDisclaimer'
import { AlertCircle, CheckCircle2, Sliders, Database, Cpu } from 'lucide-react'
import {
  modelMetricsService,
  type ModelEvaluationMetrics,
} from '@/services/model'

const formatMetric = (value: number | null) =>
  value === null || !Number.isFinite(value) ? 'Unavailable' : value.toFixed(2)

export const ModelInfoPage: React.FC = () => {
  const [metrics, setMetrics] = useState<ModelEvaluationMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    modelMetricsService
      .getMetrics()
      .then((result) => {
        if (active) setMetrics(result)
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : 'Unable to load model evaluation metrics.',
          )
        }
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-[#ebecef]">
          Model & Evaluation Metrics
        </h2>
        <p className="text-xs text-[#8d909c] font-mono mt-0.5">
          Metrics are displayed only when supplied by the configured evaluation artifact.
        </p>
      </div>

      {error && (
        <Card className="flex items-center gap-3 text-sm text-[#fca5a5]">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Mean Absolute Error (MAE)"
          value={
            metrics
              ? formatMetric(metrics.mae)
              : error
                ? 'Unavailable'
                : 'Loading'
          }
          unit="years"
          subtext={metrics?.nTestSamples ? `Test samples: ${metrics.nTestSamples}` : undefined}
          icon={<CheckCircle2 className="w-4 h-4 text-[#5eead4]" />}
        />
        <KPICard
          label="Root Mean Squared Error (RMSE)"
          value={
            metrics
              ? formatMetric(metrics.rmse)
              : error
                ? 'Unavailable'
                : 'Loading'
          }
          unit="years"
          icon={<Sliders className="w-4 h-4 text-[#8d909c]" />}
        />
        <KPICard
          label="Pearson Correlation (r)"
          value={
            metrics
              ? formatMetric(metrics.pearsonR)
              : error
                ? 'Unavailable'
                : 'Loading'
          }
          subtext="Chronological vs Predicted"
          icon={<Cpu className="w-4 h-4 text-[#5eead4]" />}
        />
        <KPICard
          label="Test samples"
          value={
            metrics?.nTestSamples == null ? (error ? 'Unavailable' : 'Loading') : metrics.nTestSamples
          }
          subtext={metrics?.datasetEvaluated ?? 'Evaluation dataset'}
          icon={<Database className="w-4 h-4 text-[#8d909c]" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="space-y-3">
          <h3 className="text-sm font-mono font-semibold uppercase tracking-wider text-[#ebecef]">
            Configured model
          </h3>
          <p className="text-sm text-[#c6c9d2]">
            Model: {metrics?.modelName ?? 'Loading'}
          </p>
          <p className="text-sm text-[#c6c9d2]">
            Architecture: {metrics?.architecture ?? 'Loading'}
          </p>
          <p className="text-sm text-[#c6c9d2]">
            Evaluation dataset: {metrics?.datasetEvaluated ?? (error ? 'Unavailable' : 'Loading')}
          </p>
          <p className="text-sm text-[#c6c9d2]">
            Last evaluated: {metrics?.lastEvaluated ?? 'Not recorded'}
          </p>
        </Card>

        <Card className="space-y-3">
          <h3 className="text-sm font-mono font-semibold uppercase tracking-wider text-[#ebecef]">
            Interpretation and limitations
          </h3>
          <p className="text-sm text-[#c6c9d2] leading-relaxed">
            Test MAE and RMSE are measured in years. Pearson correlation
            describes association, not individual prediction accuracy. Metrics
            are meaningful only for the dataset and evaluation protocol recorded
            with the model.
          </p>
          <p className="text-xs text-[#8d909c]">
            No external-cohort validation or age-bias correction is claimed by
            this page. NeuroAge is research software and is not a diagnostic
            system.
          </p>
        </Card>
      </div>

      <MedicalDisclaimer />
    </div>
  )
}
