# Step 1: Build the React app using Vite

# Use the official Node.js image as the build environment
FROM node:22 AS build

# Set the working directory
WORKDIR /app

# Copy the package.json and package-lock.json (or yarn.lock)
COPY ./frontend/package.json ./frontend/package-lock.json /app/

# Install the dependencies
RUN npm install

# Copy the entire frontend project to the container
COPY ./frontend /app

# Build the app for production
RUN npm run build


# Use the official Nginx image to serve the build
FROM nginx:alpine

# Set the environment variable for TUNEBOX_URL
ENV TUNEBOX_URL=${TUNEBOX_URL}

# Copy the custom nginx.conf file to the container
COPY ./Compose/frontend/nginx.conf /etc/nginx/nginx.conf.template

# Copy the build output from the previous stage to the nginx container
COPY --from=build /app/dist /usr/share/nginx/html

# Run envsubst at runtime to replace the TUNEBOX_URL environment variable
CMD envsubst '$TUNEBOX_URL' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g "daemon off;"

# Expose the default nginx port
EXPOSE 80

# Run nginx to serve the static files
CMD ["nginx", "-g", "daemon off;"]
