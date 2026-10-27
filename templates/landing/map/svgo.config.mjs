// Landing-only derivative of templates/assets/pagedata/DP.svg (the source
// stays untouched; the old page still inlines it). SVGO is a local dev tool,
// not a server dependency. Regenerate from the subdataversehp root:
// $ npx --yes svgo@4.1.0 --config templates/landing/map/svgo.config.mjs -i templates/assets/pagedata/DP.svg -o templates/landing/map/DP.landing.svg && sha256sum templates/assets/pagedata/DP.svg | cut -d' ' -f1 > templates/landing/map/DP.landing.svg.sha256
//
// landing.py checks DP.landing.svg.sha256 against DP.svg at build time and
// skips the preview with [LANDING] ERROR when the derivative is stale.
//
// Contract (landing.py, landing.css): nothing that renders or is referenced
// goes. Every rendered id and class, every element type, viewBox, title/desc,
// role and aria-* survive. landing.py finds partners by
// inkscape:label="rect_<label>" / "text_<label>", so those labels are kept;
// all other editor data goes. display:none subtrees (Illustrator leftovers,
// 463 kB) go; DESIGN-NOTES.md records the checks that none of them is
// referenced or shown by landing.css. Only lossless path rewrites; the
// precision is the lowest without visible change at 1440 and 375 px.
//
// One deliberate exception (2026-10-27), landingStyleHooks below: the landing
// map follows the page instead of the PowerPoint look of DP.svg. The blurred
// shadow copy of the outline goes, the artwork gets classes for landing.css
// and the partner boxes get round ends. The plugin names the DP.svg elements
// it touches and stops the run when their number differs, so a re-exported
// DP.svg cannot quietly fall back to the old look.

// Geometry (path d, polygon/polyline points) in user units. The map is drawn
// at 1771 user units and shown at most ~1400 px wide, so 1 unit < 1 px.
const GEOMETRY_PRECISION = 1;

const PARTNER_LABEL = /^(rect|text)_/;
// ns1 is Illustrator's &ns_ai; namespace, mangled into an invalid URI.
const EDITOR_PREFIXES = ['sodipodi', 'inkscape', 'ns1'];

const isEditorName = (name) => name.includes(':') && EDITOR_PREFIXES.includes(name.split(':')[0]);

// Editor elements keep only their id (sodipodi:namedview), editor attributes
// go except the partner labels; removeUnusedNS then drops unused xmlns:*.
const removeEditorDataKeepPartnerLabels = {
  name: 'removeEditorDataKeepPartnerLabels',
  fn: () => ({
    element: {
      enter: (node, parentNode) => {
        if (isEditorName(node.name)) {
          if (node.attributes.id == null) {
            parentNode.children = parentNode.children.filter((child) => child !== node);
            return;
          }
          node.attributes = { id: node.attributes.id };
          node.children = [];
          return;
        }
        for (const [name, value] of Object.entries(node.attributes)) {
          if (name === 'inkscape:label' && PARTNER_LABEL.test(value)) continue;
          if (isEditorName(name)) delete node.attributes[name];
        }
      },
    },
  }),
};

const DISPLAY_NONE = /(^|;)\s*display\s*:\s*none\s*(;|$)/;

// Only display:none, exactly. SVGO's removeHiddenElems also drops
// unreferenced clipPaths/filters and empty defs, so it stays off.
const removeDisplayNone = {
  name: 'removeDisplayNone',
  fn: () => ({
    element: {
      enter: (node, parentNode) => {
        if (node.attributes.display === 'none' || DISPLAY_NONE.test(node.attributes.style ?? '')) {
          parentNode.children = parentNode.children.filter((child) => child !== node);
          node.children = [];
        }
      },
    },
  }),
};

// DP.svg ids and colours used by landingStyleHooks (PowerPoint export).
const SHADOW_GROUP = 'g46'; // blurred copy of the outline, filter fx0
const SHADOW_DEFS = ['fx0', 'clip2', 'clip3']; // used only inside g46
const LAND = ['path54'];
const BORDER = ['path48', 'path50', 'path52'];
const RIVER_STROKE = '#0978ab';
const MARKER_FILL = '#595959';
const PARTNER_RECT = /^rect_/;
// Element counts after removeDisplayNone. A mismatch stops the run.
const EXPECTED = { shadowGroup: 1, shadowDefs: 3, land: 1, border: 3, river: 22, marker: 12, partnerRect: 14 };

const addClass = (node, name) => {
  const classes = (node.attributes.class ?? '').split(/\s+/).filter(Boolean);
  if (!classes.includes(name)) classes.push(name);
  node.attributes.class = classes.join(' ');
};

const landingStyleHooks = {
  name: 'landingStyleHooks',
  // First pass only: multipass reruns plugins on output that is already
  // restyled, and moveElemsAttrsToGroup changes the counts after pass one.
  fn: (_root, _params, info) => {
    if (info.multipassCount > 0) return null;
    const seen = Object.fromEntries(Object.keys(EXPECTED).map((key) => [key, 0]));
    return {
      element: {
        enter: (node, parentNode) => {
          const id = node.attributes.id;
          if (id === SHADOW_GROUP || SHADOW_DEFS.includes(id)) {
            seen[id === SHADOW_GROUP ? 'shadowGroup' : 'shadowDefs'] += 1;
            parentNode.children = parentNode.children.filter((child) => child !== node);
            node.children = [];
            return;
          }
          if (LAND.includes(id)) {
            addClass(node, 'map-land');
            seen.land += 1;
          }
          if (BORDER.includes(id)) {
            addClass(node, 'map-border');
            seen.border += 1;
          }
          if ((node.attributes.stroke ?? '').toLowerCase() === RIVER_STROKE) {
            addClass(node, 'map-river');
            seen.river += 1;
          }
          if ((node.attributes.fill ?? '').toLowerCase() === MARKER_FILL) {
            addClass(node, 'map-marker');
            seen.marker += 1;
          }
          if (node.name === 'rect' && PARTNER_RECT.test(node.attributes['inkscape:label'] ?? '')) {
            // Round ends as an attribute (works where CSS rx does not), and no
            // inline stroke-width (rect_h-brs), which would beat landing.css.
            node.attributes.rx = String(Number(node.attributes.height) / 2);
            const kept = (node.attributes.style ?? '')
              .split(';')
              .map((declaration) => declaration.trim())
              .filter((declaration) => declaration && !/^stroke-(width|dasharray)\s*:/.test(declaration));
            if (kept.length) node.attributes.style = kept.join(';');
            else delete node.attributes.style;
            seen.partnerRect += 1;
          }
        },
      },
      root: {
        exit: () => {
          const off = Object.keys(EXPECTED).filter((key) => seen[key] !== EXPECTED[key]);
          if (off.length) {
            const detail = off.map((key) => `${key} ${seen[key]} (expected ${EXPECTED[key]})`).join(', ');
            throw new Error(`landingStyleHooks: DP.svg no longer matches: ${detail}`);
          }
        },
      },
    };
  },
};

export default {
  multipass: true,
  js2svg: { pretty: false },
  plugins: [
    removeDisplayNone,
    landingStyleHooks,
    removeEditorDataKeepPartnerLabels,
    {
      name: 'preset-default',
      params: {
        overrides: {
          // Replaced by removeEditorDataKeepPartnerLabels above.
          removeEditorsNSData: false,
          // Keep every rendered id, element and element type.
          cleanupIds: false,
          removeHiddenElems: false,
          removeEmptyContainers: false,
          removeEmptyText: false,
          removeUselessDefs: false,
          collapseGroups: false,
          convertShapeToPath: false,
          convertEllipseToCircle: false,
          mergePaths: false,
          removeDesc: false,
          removeUnknownsAndDefaults: { keepRoleAttr: true, keepAriaAttrs: true, keepDataAttrs: true },
          // Stroke widths, x/y/width/height: keep their precision.
          cleanupNumericValues: { floatPrecision: 3 },
          // Lossless rewrites only: no arcs or lines fitted to curves.
          convertPathData: {
            floatPrecision: GEOMETRY_PRECISION,
            makeArcs: false,
            straightCurves: false,
            convertToQ: false,
            smartArcRounding: false,
          },
        },
      },
    },
    { name: 'cleanupListOfValues', params: { floatPrecision: GEOMETRY_PRECISION } },
  ],
};
