<!-- W-090 (REQ-034 AC-6): the At Expiry / Estimated Now switch for the scenario columns. It only sends the pick (an
     event); every level and number comes back from the outcome API. The estimate label is the server's own text
     (scenario.label), shown whenever the Estimated Now column is on.
     GC-UI b1 (D-B04, D-B10; Sensibull 012 has one header row and no range inputs): the From / To / Apply range /
     Default range controls are gone; the range is the payoff graph's Zoom (PayoffChart), which still asks the engine
     for points over the new range (REQ-083 AC-7, REQ-034 AC-4). The switch is compact, in the Payoff header row. -->
<script setup>
import { VIEWS } from '@/lib/scenarioChoice'
import FigureHint from '@/components/common/FigureHint.vue'
import Tooltip from '@/components/common/Tooltip.vue'

const props = defineProps({
  choice: { type: Object, required: true },
  scenarioLabel: { type: String, default: '' },
  // W-193 (I-9): the reply's data label (for example "estimated from spot"), the tooltip beside the Estimated Now switch;
  // the server's text as sent.
  estimateNote: { type: String, default: '' },
})
const emit = defineEmits(['update:choice'])

const set = (patch) => emit('update:choice', { ...props.choice, ...patch })
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 text-xs" data-testid="scenario-controls">
    <div class="inline-flex items-center gap-1 rounded-md border border-line p-0.5" role="group" aria-label="Scenario column">
      <button
        v-for="v in VIEWS"
        :key="v.key"
        type="button"
        :data-testid="`view-${v.key}`"
        :aria-pressed="choice.view === v.key"
        :class="['rounded px-2 py-0.5 font-medium', choice.view === v.key ? 'bg-accent text-surface' : 'text-ink-muted hover:text-ink']"
        @click="set({ view: v.key })"
      >
        {{ v.label }}
      </button>
      <span v-if="estimateNote" data-testid="estimate-note"><Tooltip :text="estimateNote" label="About the price data of the estimate" /></span>
    </div>
    <span v-if="choice.view === 'estimated_now' && scenarioLabel" class="flex items-center">
      <span class="text-ink-muted" data-testid="scenario-label">{{ scenarioLabel }}</span>
      <FigureHint id="estimated_now" />
    </span>
  </div>
</template>
