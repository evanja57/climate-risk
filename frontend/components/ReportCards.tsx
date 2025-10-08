import { SourceAwareText, type SourcesMap } from "@/components/SourceAwareText"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AlertCircle, TrendingUp, Target, Activity, Layers, Lightbulb, AlertTriangle } from "lucide-react"

type ReportData = {
  sources?: SourcesMap
  company?: {
    company_name?: string
    identity_verification?: string
    sector_classification?: string
    transition_positioning?: string
    net_zero_targets?: Array<{
      target_type?: string
      target_year?: string
      status?: string
      detail?: string
      source?: string
    }>
    decarbonisation_programmes?: Array<{
      programme?: string
      mechanism?: string
      investment_signal?: string
      status?: string
      source?: string
    }>
    climate_governance?: string
    policy_engagement?: string
    data_gaps?: string[]
    key_sources?: string[]
  }
  risk_assessment?: {
    overall_transition_risk_rating?: string
    risk_matrix?: Array<{
      risk_driver?: string
      exposure_description?: string
      financial_transmission?: string
      time_horizon?: string
      probability?: string
      severity?: string
      mitigation_status?: string
      source?: string
    }>
  }
  metrics_targets?: {
    emissions_profile?: string
    capital_alignment?: string
    product_portfolio_shift?: string
    just_transition_considerations?: string
    metric_gaps?: string[]
  }
  transition_overlay?: {
    what_to_overlay?: Array<{
      overlay?: string
      why?: string
      sources?: string[]
    }>
    scenario_families?: any[]
    sector_pathways?: any[]
    policy_envelopes?: any[]
    overlays?: any[]
  }
  scenario_analysis?: {
    methodology_note?: string
    orderly_net_zero_2050?: string
    accelerated_policy_shock?: string
    delayed_transition?: string
    signposts_to_monitor?: string[]
  }
  recommendations?: {
    strategic_actions?: string[]
    disclosure_improvements?: string[]
    engagement_questions?: string[]
  }
  limitations?: string
}

export function ReportCards({ data }: { data: ReportData }) {
  const sources = data.sources

  const getRiskColor = (rating?: string) => {
    if (!rating) return "bg-gray-100 text-gray-800"
    const lower = rating.toLowerCase()
    if (lower.includes("low")) return "bg-green-100 text-green-800"
    if (lower.includes("moderate")) return "bg-yellow-100 text-yellow-800"
    if (lower.includes("high")) return "bg-orange-100 text-orange-800"
    if (lower.includes("severe")) return "bg-red-100 text-red-800"
    return "bg-gray-100 text-gray-800"
  }

  const getStatusColor = (status?: string) => {
    if (!status) return "bg-gray-100 text-gray-800"
    const lower = status.toLowerCase()
    if (lower.includes("on track") || lower.includes("completed")) return "bg-green-100 text-green-800"
    if (lower.includes("in progress") || lower.includes("announced")) return "bg-blue-100 text-blue-800"
    if (lower.includes("off track")) return "bg-red-100 text-red-800"
    return "bg-gray-100 text-gray-800"
  }

  return (
    <div className="space-y-6">
      {/* Company Overview */}
      {data.company && (
        <Card className="shadow-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Company Overview
            </CardTitle>
            {data.company.company_name && (
              <CardDescription className="text-lg font-semibold text-foreground">
                {data.company.company_name}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {data.company?.identity_verification && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Identity Verification</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.company?.identity_verification} sources={sources} />
                </p>
              </div>
            )}
            {data.company?.sector_classification && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Sector Classification</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.company?.sector_classification} sources={sources} />
                </p>
              </div>
            )}
            {data.company?.transition_positioning && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Transition Positioning</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.company?.transition_positioning} sources={sources} />
                </p>
              </div>
            )}
            {data.company?.climate_governance && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Climate Governance</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.company?.climate_governance} sources={sources} />
                </p>
              </div>
            )}
            {data.company?.policy_engagement && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Policy Engagement</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.company?.policy_engagement} sources={sources} />
                </p>
              </div>
            )}
            {data.company.data_gaps && data.company.data_gaps.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-2">Data Gaps</h4>
                <div className="flex flex-wrap gap-2">
                  {data.company.data_gaps.map((gap, idx) => (
                    <Badge key={idx} variant="outline" className="bg-amber-50">
                      {gap}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Net Zero Targets */}
      {data.company?.net_zero_targets && data.company.net_zero_targets.length > 0 && (
        <Card className="shadow-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              Net Zero Targets
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {data.company.net_zero_targets.map((target, idx) => (
                <div key={idx} className="border-l-4 border-primary pl-4 py-2">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="font-semibold text-sm">
                      {target.target_type} {target.target_year && `(${target.target_year})`}
                    </span>
                    {target.status && <Badge className={getStatusColor(target.status)}>{target.status}</Badge>}
                  </div>
                  {target.detail && (
                    <p className="text-sm text-muted-foreground">
                      <SourceAwareText text={target.detail} sources={sources} />
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Decarbonisation Programmes */}
      {data.company?.decarbonisation_programmes && data.company.decarbonisation_programmes.length > 0 && (
        <Card className="shadow-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Decarbonisation Programmes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {data.company.decarbonisation_programmes.map((prog, idx) => (
                <div key={idx} className="border rounded-lg p-3 bg-muted/30">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="font-semibold text-sm">{prog.programme}</span>
                    {prog.status && <Badge className={getStatusColor(prog.status)}>{prog.status}</Badge>}
                  </div>
                  {prog.mechanism && (
                    <p className="text-sm text-muted-foreground mb-1">
                      <span className="font-medium">Mechanism:</span>{" "}
                      <SourceAwareText text={prog.mechanism} sources={sources} />
                    </p>
                  )}
                  {prog.investment_signal && (
                    <p className="text-sm text-muted-foreground">
                      <span className="font-medium">Investment:</span>{" "}
                      <SourceAwareText text={prog.investment_signal} sources={sources} />
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Risk Assessment */}
      {data.risk_assessment && (
        <Card className="shadow-md border-l-4 border-l-orange-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Risk Assessment
            </CardTitle>
            {data.risk_assessment.overall_transition_risk_rating && (
              <div className="mt-2">
                <Badge
                  variant="outline"
                  className={`${getRiskColor(data.risk_assessment.overall_transition_risk_rating)} text-base px-3 py-1`}
                >
                  {data.risk_assessment.overall_transition_risk_rating}
                </Badge>
              </div>
            )}
          </CardHeader>
          <CardContent>
            {data.risk_assessment.risk_matrix && data.risk_assessment.risk_matrix.length > 0 && (
              <div className="space-y-3">
                <h4 className="font-semibold text-sm">Risk Matrix</h4>
                {data.risk_assessment.risk_matrix.map((risk, idx) => (
                  <div key={idx} className="border rounded-lg p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold text-sm">{risk.risk_driver}</span>
                      <div className="flex gap-2">
                        {risk.probability && (
                          <Badge variant="outline" className="text-xs">
                            Probability: {risk.probability}
                          </Badge>
                        )}
                        {risk.severity && (
                          <Badge variant="outline" className="text-xs">
                            Severity: {risk.severity}
                          </Badge>
                        )}
                      </div>
                    </div>
                    {risk.exposure_description && (
                      <p className="text-sm text-muted-foreground">
                        <SourceAwareText text={risk.exposure_description} sources={sources} />
                      </p>
                    )}
                    {risk.financial_transmission && (
                      <p className="text-sm">
                        <span className="font-medium">Financial impact:</span>{" "}
                        <SourceAwareText text={risk.financial_transmission} sources={sources} />
                      </p>
                    )}
                    <div className="flex flex-wrap gap-2 text-xs">
                      {risk.time_horizon && <Badge variant="secondary">{risk.time_horizon}</Badge>}
                      {risk.mitigation_status && (
                        <Badge variant="outline" className="bg-blue-50">
                          {risk.mitigation_status}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Metrics & Targets */}
      {data.metrics_targets && (
        <Card className="shadow-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="h-5 w-5" />
              Metrics & Targets
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.metrics_targets.emissions_profile && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Emissions Profile</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.metrics_targets.emissions_profile} sources={sources} />
                </p>
              </div>
            )}
            {data.metrics_targets.capital_alignment && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Capital Alignment</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.metrics_targets.capital_alignment} sources={sources} />
                </p>
              </div>
            )}
            {data.metrics_targets.product_portfolio_shift && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Product Portfolio Shift</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.metrics_targets.product_portfolio_shift} sources={sources} />
                </p>
              </div>
            )}
            {data.metrics_targets.just_transition_considerations && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Just Transition Considerations</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.metrics_targets.just_transition_considerations} sources={sources} />
                </p>
              </div>
            )}
            {data.metrics_targets.metric_gaps && data.metrics_targets.metric_gaps.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-2">Metric Gaps</h4>
                <div className="flex flex-wrap gap-2">
                  {data.metrics_targets.metric_gaps.map((gap, idx) => (
                    <Badge key={idx} variant="outline" className="bg-amber-50">
                      {gap}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Scenario Analysis */}
      {data.scenario_analysis && (
        <Card className="shadow-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Scenario Analysis
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.scenario_analysis.methodology_note && (
              <div className="bg-muted/50 p-3 rounded-lg">
                <p className="text-sm text-muted-foreground italic">
                  <SourceAwareText text={data.scenario_analysis.methodology_note} sources={sources} />
                </p>
              </div>
            )}
            {data.scenario_analysis.orderly_net_zero_2050 && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Orderly Net Zero 2050</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.scenario_analysis.orderly_net_zero_2050} sources={sources} />
                </p>
              </div>
            )}
            {data.scenario_analysis.accelerated_policy_shock && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Accelerated Policy Shock</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.scenario_analysis.accelerated_policy_shock} sources={sources} />
                </p>
              </div>
            )}
            {data.scenario_analysis.delayed_transition && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Delayed Transition</h4>
                <p className="text-sm text-muted-foreground">
                  <SourceAwareText text={data.scenario_analysis.delayed_transition} sources={sources} />
                </p>
              </div>
            )}
            {data.scenario_analysis.signposts_to_monitor && data.scenario_analysis.signposts_to_monitor.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-2">Signposts to Monitor</h4>
                <ul className="list-disc list-inside space-y-1">
                  {data.scenario_analysis.signposts_to_monitor.map((signpost, idx) => (
                    <li key={idx} className="text-sm text-muted-foreground">
                      <SourceAwareText text={signpost} sources={sources} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Recommendations */}
      {data.recommendations && (
        <Card className="shadow-md border-l-4 border-l-blue-500">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="h-5 w-5" />
              Recommendations
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.recommendations.strategic_actions && data.recommendations.strategic_actions.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-2">Strategic Actions</h4>
                <ul className="list-disc list-inside space-y-1">
                  {data.recommendations.strategic_actions.map((action, idx) => (
                    <li key={idx} className="text-sm text-muted-foreground">
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.recommendations.disclosure_improvements &&
              data.recommendations.disclosure_improvements.length > 0 && (
                <div>
                  <h4 className="font-semibold text-sm mb-2">Disclosure Improvements</h4>
                  <ul className="list-disc list-inside space-y-1">
                    {data.recommendations.disclosure_improvements.map((improvement, idx) => (
                      <li key={idx} className="text-sm text-muted-foreground">
                        {improvement}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            {data.recommendations.engagement_questions && data.recommendations.engagement_questions.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-2">Engagement Questions</h4>
                <ul className="list-disc list-inside space-y-1">
                  {data.recommendations.engagement_questions.map((question, idx) => (
                    <li key={idx} className="text-sm text-muted-foreground">
                      {question}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Limitations */}
      {data.limitations && (
        <Card className="shadow-md bg-amber-50/50">
          <CardHeader>
            <CardTitle className="text-base">Limitations</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              <SourceAwareText text={data.limitations} sources={sources} />
            </p>
          </CardContent>
        </Card>
      )}

      {sources && Object.keys(sources).length > 0 && (
        <Card id="sources" className="shadow-md scroll-mt-24">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">Sources</CardTitle>
            <CardDescription>References cited throughout the report</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3 list-decimal list-inside text-sm">
              {Object.entries(sources)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([id, src]) => (
                  <li key={id} id={`source-${id}`} tabIndex={-1} className="scroll-mt-24">
                    {src.label && <span className="font-semibold">{src.label} — </span>}
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary underline hover:text-primary/80 break-all"
                    >
                      {src.url}
                    </a>
                  </li>
                ))}
            </ol>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
