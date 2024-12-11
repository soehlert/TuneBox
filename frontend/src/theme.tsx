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
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: "#0077B6", // Purple from logo
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
    MuiButton: {
      styleOverrides: {
        // Override for "First" and "Previous" buttons
        root: {
          '&.pagination-first-prev': {
            backgroundColor: '#6f7577', // Lighter gray for First and Previous buttons
            color: 'white',
            '&:hover': {
              backgroundColor: '#90A4AE', // Darker gray on hover
            },
          },
          '&.pagination-next-last': {
            backgroundColor: '#6f7577', // Lighter gray for First and Previous buttons
            color: 'white',
            '&:hover': {
              backgroundColor: '#90A4AE', // Darker gray on hover
            },
          },
        },
      },
    },
  },
});

export default theme;
