import { createUnifiedTheme, palettes, defaultTypography } from '@backstage/theme';

const page = {
  colors: ['#05080f', '#05080f'],
  shape: 'none',
  backgroundImage: 'none',
  fontColor: '#ffffff',
};

// The shared theme covers Backstage's Material UI v4 and v5 components.
export const aivenTheme = createUnifiedTheme({
  palette: {
    ...palettes.dark,
    primary: { main: '#5ffa74', dark: '#44dc5b', light: '#8dff9c', contrastText: '#05080f' },
    secondary: { main: '#a49cff', contrastText: '#05080f' },
    background: { default: '#05080f', paper: '#0d0e10' },
    text: { primary: '#ffffff', secondary: '#a6adb9', disabled: '#7f899a' },
    divider: '#2d2e30',
    border: '#2d2e30',
    link: '#b9b3ff',
    linkHover: '#d1cdff',
    navigation: { background: '#05080f', color: '#a6adb9', selectedColor: '#ffffff', indicator: '#5ffa74' },
    tabbar: { indicator: '#5ffa74' },
  },
  fontFamily: 'Inter, sans-serif',
  typography: {
    ...defaultTypography,
    fontFamily: 'Inter, sans-serif',
    h1: { fontFamily: 'Funnel Display, sans-serif', fontSize: 48, fontWeight: 800, marginBottom: 12 },
    h2: { fontFamily: 'Funnel Display, sans-serif', fontSize: 28, fontWeight: 800, marginBottom: 12 },
    h3: { fontFamily: 'Inter, sans-serif', fontSize: 22, fontWeight: 600, marginBottom: 8 },
    h4: { fontFamily: 'Inter, sans-serif', fontSize: 20, fontWeight: 600, marginBottom: 8 },
  },
  defaultPageTheme: 'home',
  pageTheme: Object.fromEntries(['home', 'website', 'app', 'service', 'documentation', 'tool', 'library', 'other'].map(key => [key, page])),
  components: {
    MuiButton: { styleOverrides: {
      root: { borderRadius: 100, textTransform: 'none', fontWeight: 600, padding: '10px 22px', minHeight: 44, boxShadow: 'none' },
      containedPrimary: { '&:hover': { backgroundColor: '#8dff9c', boxShadow: 'none' } },
    } },
    MuiPaper: { styleOverrides: {
      root: { backgroundImage: 'none' },
      rounded: { borderRadius: 12 },
      elevation1: { boxShadow: 'none', border: '1px solid #2d2e30' },
    } },
    MuiCardHeader: { styleOverrides: { root: { padding: '28px 32px' }, subheader: { marginTop: 8, lineHeight: 1.6 } } },
    MuiCardContent: { styleOverrides: { root: { padding: 28 } } },
    MuiInputBase: { styleOverrides: { root: { fontSize: 15 }, input: { paddingTop: 12, paddingBottom: 12 } } },
    MuiFormHelperText: { styleOverrides: { root: { fontSize: 12, lineHeight: 1.6, marginTop: 8 } } },
    MuiStepIcon: { styleOverrides: { root: { color: '#42464f' }, text: { fill: '#05080f', fontWeight: 600 } } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 500 } } },
    MuiChip: { styleOverrides: { root: { borderRadius: 6 } } },
  },
});
