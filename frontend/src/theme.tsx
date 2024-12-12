import { createTheme } from "@mui/material/styles";

// Create theme with custom colors
const theme = createTheme({
  palette: {
    primary: {
      main: "#E59500", // Orange accent for primary buttons
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
      color: "#E59500", // Orange for h2 (secondary heading)
    },
    h3: {
      color: "#E59500",
    },
    h4: {
      color: "#E59500",
      fontSize: "2rem", // Set font size for h3
      fontWeight: "bold", // Bold text
      textAlign: "center", // Center-align text
      textTransform: "uppercase", // Uppercase letters
      letterSpacing: "2px", // Add spacing between letters
      textShadow: "2px 2px 5px rgba(0, 0, 0, 0.4)", // Add text shadow for a glowing effect
    },
    body1: {
      color: "#EEEEEE", // Light gray for body text
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: "#0077B6",
          color: "#FFFFFF", // White text color for all cards
          boxShadow: "0 2px 5px rgba(0, 0, 0, 0.3)", // Box shadow for depth
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: "#0077B6", // Set background color to purple from logo
          color: "#FFFFFF", // Set text color to white to ensure visibility
        },
      },
    },
  },
});

export default theme;
