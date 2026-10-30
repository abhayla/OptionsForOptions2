// GC-ADJ1 step 1b (W-196): the server says, in GET /features `scenario`, when it serves a scenario of the adjustment
// library (dev/test only; ofo_app.scenario_mode). Every screen then shows "Scenario ADJ-xx - test data, not the
// market". Answer states (standing item d):
//   stated, an ADJ id (ADJ-02, ADJ-20a)       -> the banner names it;
//   null / field absent                         -> no banner (the server serves the market);
//   any other value (a sentence, a number, "") -> a banner WITHOUT the id ("Scenario - test data, not the market"):
//                                                 the server said something is set, so never hide the warning;
//   request failed                               -> no banner (the server also refuses scenario mode outside dev/test).
import { ref } from "vue";
import { fetchFeaturesBody } from "./orderPath";

const SCENARIO_ID = /^ADJ-[0-9]{2}[a-e]?$/;

/** The banner sentence for a /features body, or null when no scenario is served. */
export function scenarioBanner(body) {
  if (
    !body ||
    typeof body !== "object" ||
    body.scenario === undefined ||
    body.scenario === null
  )
    return null;
  const id = body.scenario;
  if (typeof id === "string" && SCENARIO_ID.test(id))
    return `Scenario ${id} - test data, not the market`;
  return "Scenario - test data, not the market";
}

/** A ref holding the banner sentence (null until and unless the server names a scenario). */
export function useScenarioBanner() {
  const text = ref(null);
  fetchFeaturesBody().then((body) => {
    text.value = scenarioBanner(body);
  });
  return text;
}
