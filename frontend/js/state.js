// Application state store with a tiny pub/sub layer.

const listeners = new Set();

export const state = {
  schema: null,
  project: null,
  selection: null,      // node id
  zoom: 1,
  showGrid: true,
  snap: true,
  preview: false,
  codeMode: 'template',
  generated: { template: '', yaml: '', payload: [] },
  dirty: false,
  settings: { haUrl: '', deviceId: '', service: '', hasToken: false },
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit(event = 'change') {
  for (const fn of listeners) fn(event, state);
}

export function setState(patch, event = 'change') {
  Object.assign(state, patch);
  emit(event);
}

let uidCounter = 0;
export function uid(prefix = 'n') {
  uidCounter += 1;
  return `${prefix}${Date.now().toString(36)}${uidCounter.toString(36)}`;
}

export function createProject(name = 'Untitled') {
  return {
    id: null,
    name,
    width: 296,
    height: 128,
    background: 'white',
    nodes: [],
    variables: [],
  };
}

export function findNode(id, nodes = state.project?.nodes || []) {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findNode(id, node.children);
      if (found) return found;
    }
  }
  return null;
}

export function findParent(id, nodes = state.project?.nodes || [], parent = null) {
  for (const node of nodes) {
    if (node.id === id) return { parent, list: nodes, index: nodes.indexOf(node) };
    if (node.children) {
      const found = findParent(id, node.children, node);
      if (found) return found;
    }
  }
  return null;
}

export function removeNode(id) {
  const location = findParent(id);
  if (!location) return null;
  location.list.splice(location.index, 1);
  return location;
}

export function defaultProps(type) {
  const spec = state.schema?.types.find((t) => t.type === type);
  const props = {};
  if (spec) {
    for (const field of spec.fields) props[field.key] = field.default;
  }
  return props;
}

export function typeSpec(type) {
  return state.schema?.types.find((t) => t.type === type) || null;
}

export function createElement(type, overrides = {}) {
  return {
    id: uid('el'),
    kind: 'element',
    type,
    props: { ...defaultProps(type), ...overrides },
  };
}

export function createGroup(children = []) {
  return {
    id: uid('grp'),
    kind: 'group',
    name: 'Repeat group',
    repeat: { enabled: true, var: 'i', count: 8, pre: [] },
    children,
  };
}
