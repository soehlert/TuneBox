// theme.tsx
import { createTheme } from "@mui/material/styles";

// Create theme with custom colors
const theme = createTheme({
  palette: {
    primary: {
      main: "#DC5F00", // Orange accent for primary buttons
    },
    secondary: {
      main: "#2C4E80", // Blue for secondary buttons and highlights
    },
    background: {
      default: "#373A40", // Dark gray background for the app
    },
    text: {
      primary: "#EEEEEE", // Light gray text color
      secondary: "#686D76", // Muted gray for secondary text
    },
  },
  typography: {
    h1: {
      color: "#EEEEEE", // Light gray for h1 (primary heading)
    },
    h2: {
      color: "#DC5F00", // Orange for h2 (secondary heading)
    },
    body1: {
      color: "#EEEEEE", // Light gray for body text
    },
  },
});

export default theme;
