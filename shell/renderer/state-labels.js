(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.jarvisStateLabels = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const AGENT_STATE_LABELS = {
    idle: 'boşta',
    listening: 'dinliyor',
    thinking: 'düşünüyor',
    speaking: 'konuşuyor',
    error: 'hata',
  };

  function describeAgentState(state) {
    return AGENT_STATE_LABELS[state] || state;
  }

  return { AGENT_STATE_LABELS, describeAgentState };
});
