import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  Code,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  computeDAGLayout,
  useHostTheme,
} from "cursor/canvas";

const PIPELINE_NODES = [
  { id: "trigger" },
  { id: "prepare" },
  { id: "architect" },
  { id: "security" },
  { id: "performance" },
  { id: "quality" },
  { id: "dedup" },
  { id: "repair_gate" },
  { id: "repair" },
  { id: "deliver" },
  { id: "ui" },
];

const PIPELINE_EDGES = [
  { from: "trigger", to: "prepare" },
  { from: "prepare", to: "architect" },
  { from: "architect", to: "security" },
  { from: "architect", to: "performance" },
  { from: "architect", to: "quality" },
  { from: "security", to: "dedup" },
  { from: "performance", to: "dedup" },
  { from: "quality", to: "dedup" },
  { from: "dedup", to: "repair_gate" },
  { from: "repair_gate", to: "repair" },
  { from: "repair", to: "deliver" },
  { from: "deliver", to: "ui" },
];

const NODE_LABELS: Record<string, string> = {
  trigger: "Trigger",
  prepare: "Prepare context",
  architect: "Architect",
  security: "Security",
  performance: "Performance",
  quality: "Code quality",
  dedup: "Validate + dedup",
  repair_gate: "Repair gate",
  repair: "Repair agent",
  deliver: "Fix delivery",
  ui: "Dashboard",
};

function PipelineGraph() {
  const theme = useHostTheme();
  const layout = computeDAGLayout({
    nodes: PIPELINE_NODES,
    edges: PIPELINE_EDGES,
    direction: "vertical",
    nodeWidth: 148,
    nodeHeight: 42,
    rankGap: 52,
    nodeGap: 20,
    padding: 16,
  });

  const nodeById = Object.fromEntries(layout.nodes.map((n) => [n.id, n]));

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role="img"
      aria-label="Pulse agent quality review pipeline"
    >
      {layout.edges.map((edge) => {
        const midY = (edge.sourceY + edge.targetY) / 2;
        const d = `M ${edge.sourceX} ${edge.sourceY} C ${edge.sourceX} ${midY}, ${edge.targetX} ${midY}, ${edge.targetX} ${edge.targetY}`;
        return (
          <path
            key={`${edge.from}-${edge.to}`}
            d={d}
            fill="none"
            stroke={theme.stroke.secondary}
            strokeWidth={1.5}
          />
        );
      })}
      {layout.nodes.map((node) => (
        <g key={node.id}>
          <rect
            x={node.x}
            y={node.y}
            width={148}
            height={42}
            rx={6}
            fill={theme.fill.secondary}
            stroke={
              node.id === "dedup" || node.id === "repair_gate"
                ? theme.accent.primary
                : theme.stroke.primary
            }
            strokeWidth={node.id === "dedup" || node.id === "repair_gate" ? 1.5 : 1}
          />
          <text
            x={node.x + 74}
            y={node.y + 25}
            textAnchor="middle"
            fill={theme.text.primary}
            fontSize={11}
          >
            {NODE_LABELS[node.id]}
          </text>
        </g>
      ))}
      {nodeById.architect && nodeById.dedup ? (
        <text
          x={layout.width - 8}
          y={nodeById.architect.y + 70}
          textAnchor="end"
          fill={theme.text.tertiary}
          fontSize={10}
        >
          docs-only skips agents
        </text>
      ) : null}
    </svg>
  );
}

export default function AgentQualityWorkflow() {
  return (
    <Stack gap={28}>
      <Stack gap={8}>
        <H1>Pulse agent quality workflow</H1>
        <Text tone="secondary">
          End-to-end review pipeline implemented in the agent quality overhaul:
          richer context, evidence checks, confidence gates, patch validation,
          and optional auto-delivery of fixes.
        </Text>
      </Stack>

      <Callout tone="info" title="Problem this workflow solves">
        Agents were producing duplicate findings, hallucinated issues, broken
        patches, and false positives because they saw only a raw diff. The
        pipeline now builds file context first, then filters, then repairs only
        high-confidence issues.
      </Callout>

      <Grid columns={4} gap={12}>
        <Stat value="4" label="Implementation phases" />
        <Stat value="3" label="Reviewer agents in parallel" />
        <Stat value="0.7" label="Default repair confidence floor" />
        <Stat value="5" label="Max findings per agent" />
      </Grid>

      <H2>Live review pipeline</H2>
      <Text tone="secondary" size="small">
        LangGraph graph in packages/orchestrator/app/graph/builder.py. Accent
        border marks the two quality choke points: validation/dedup and the
        repair gate.
      </Text>
      <PipelineGraph />

      <H2>What each stage does</H2>
      <Table
        headers={["Stage", "Quality control", "Key files"]}
        rows={[
          [
            "Trigger",
            "CLI, dashboard, or API sends the diff plus project_root",
            "review.ts · main.py · review_runner.py",
          ],
          [
            "Prepare context",
            "Parse hunks, read full files, imports, siblings, tests",
            "diff_parser.py · context_builder.py",
          ],
          [
            "Architect",
            "Rules-based routing; skip docs-only diffs",
            "architect_agent.py",
          ],
          [
            "Reviewer agents",
            "Anti-hallucination prompts, evidence snippets, confidence scores",
            "base_reviewer.py · security/performance/quality agents",
          ],
          [
            "Validate + dedup",
            "Drop findings without evidence, wrong file/line, or weak confidence; merge same-category duplicates",
            "finding_validator.py · finding_filters.py · dedup.py",
          ],
          [
            "Repair gate",
            "Only critical/warning findings at confidence ≥ 0.7",
            "builder.py repair_gate",
          ],
          [
            "Repair",
            "Patch against full file; git apply --check; UNVERIFIED if Docker is down",
            "repair_agent.py · patch_validator.py · repair_runner.py",
          ],
          [
            "Fix delivery",
            "ask (manual) · local · PR comment · GitHub branch with real blobs",
            "fix_applicator.py · SettingsPanel",
          ],
        ]}
        rowTone={[
          "neutral",
          "info",
          "info",
          "neutral",
          "success",
          "warning",
          "warning",
          "success",
        ]}
      />

      <H2>Quality gates in order</H2>
      <Grid columns={2} gap={16}>
        <Stack gap={10}>
          <H3>Finding quality</H3>
          <Text>
            Each finding must include an <Code>evidence</Code> snippet that
            actually appears in the diff. Strict validation also checks file
            membership, line mapping, and domain category slugs.
          </Text>
          <Text>
            Post-parse filters drop low-confidence items and cap each agent at
            5 findings so the repair agent is not flooded.
          </Text>
          <Row gap={8} wrap>
            <Pill tone="success" active>
              Evidence required
            </Pill>
            <Pill tone="warning" active>
              Confidence floor
            </Pill>
            <Pill active>Max 5 / agent</Pill>
          </Row>
        </Stack>
        <Stack gap={10}>
          <H3>Repair quality</H3>
          <Text>
            The repair agent receives the authoritative file, not just the
            hunk. Suggested reviewer fixes are labeled as unverified hints.
          </Text>
          <Text>
            Patches are checked with git apply before Docker tests. If Docker
            is unavailable the status is UNVERIFIED, not succeeded.
          </Text>
          <Row gap={8} wrap>
            <Pill tone="info" active>
              Full-file patch
            </Pill>
            <Pill tone="warning" active>
              git apply --check
            </Pill>
            <Pill tone="warning" active>
              UNVERIFIED without Docker
            </Pill>
          </Row>
        </Stack>
      </Grid>

      <H2>Implemented in four phases</H2>
      <Grid columns={2} gap={12}>
        <Card>
          <CardHeader trailing={<Pill tone="success" active>Done</Pill>}>
            Phase 1 — Signal quality
          </CardHeader>
          <CardBody>
            <Text size="small">
              Evidence field, UNVERIFIED repair status, quality settings,
              stricter prompts, confidence gate, same-category dedup, repair
              only for critical/warning ≥ 0.7.
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="success" active>Done</Pill>}>
            Phase 2 — Context
          </CardHeader>
          <CardBody>
            <Text size="small">
              Structured diff parser, context builder, finding validator,
              shared base reviewer, architect skip for docs, graph state with
              project_root / file_context / parsed_hunks.
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="success" active>Done</Pill>}>
            Phase 3 — Patches
          </CardHeader>
          <CardBody>
            <Text size="small">
              Patch validator, repair against full file, hunk-only original
              diff, repair_max_attempts from settings, Docker-unavailable
              marked UNVERIFIED.
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="success" active>Done</Pill>}>
            Phase 4 — Feedback loop
          </CardHeader>
          <CardBody>
            <Text size="small">
              Unit tests, false-positive button, evidence in Findings panel,
              quality thresholds in Settings, CLI sends project_root,
              auto-deliver via fix_delivery, real GitHub branch commits.
            </Text>
          </CardBody>
        </Card>
      </Grid>

      <H2>Repair and delivery path</H2>
      <Text>
        After a patch is produced, delivery is separate from generation. Default
        is still Ask so the dashboard buttons apply the fix. Other modes run
        automatically after a successful or unverified repair.
      </Text>
      <Table
        headers={["fix_delivery", "When it runs", "What happens"]}
        rows={[
          [
            "ask",
            "Manual",
            "Apply Locally / PR Comment / Commit to Branch on the repair card",
          ],
          [
            "local",
            "Auto after repair",
            "git apply (or Python fallback) on the project; no commit",
          ],
          [
            "pr_comment",
            "Auto if repo + PR exist",
            "Posts the patch as a GitHub PR comment",
          ],
          [
            "branch",
            "Auto if repo + PR exist",
            "Creates pulse/fix-{review_id} with blob → tree → commit",
          ],
        ]}
        rowTone={["neutral", "info", "info", "success"]}
      />

      <Divider />

      <H2>Before vs after</H2>
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>Before</H3>
          <Text size="small">Agents reviewed a raw diff with no file context.</Text>
          <Text size="small">Duplicates merged across unrelated categories.</Text>
          <Text size="small">First finding could force a repair attempt.</Text>
          <Text size="small">Missing Docker was reported as a successful repair.</Text>
          <Text size="small">Branch “commit” stored the patch in the message only.</Text>
        </Stack>
        <Stack gap={8}>
          <H3>After</H3>
          <Text size="small">Hunks plus full file, imports, siblings, and tests.</Text>
          <Text size="small">Dedup only when category matches; evidence required.</Text>
          <Text size="small">Repair only for high-confidence critical/warning.</Text>
          <Text size="small">UNVERIFIED until Docker tests pass.</Text>
          <Text size="small">Git Data API writes real file blobs on the fix branch.</Text>
        </Stack>
      </Grid>

      <Callout tone="warning" title="Known gap outside this workflow">
        Local GitHub automation (hooks install, one-shot run-review, optional
        daemon) was planned separately and is not part of this quality pipeline.
      </Callout>
    </Stack>
  );
}
