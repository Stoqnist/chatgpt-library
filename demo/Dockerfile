FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html style.css journey.css app.js cases.js /usr/share/nginx/html/
COPY assets/stoqnist-banner.svg assets/stoqnist-banner-mobile.svg assets/everyday-room.webp /usr/share/nginx/html/assets/
USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
