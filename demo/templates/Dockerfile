FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY locale-routes.conf /etc/nginx/locale-routes.conf
COPY index.html style.css journey.css brand-journey.css localization.css app.js cases.js i18n.js /usr/share/nginx/html/
COPY assets/stoqnist-banner.svg assets/stoqnist-banner-mobile.svg /usr/share/nginx/html/assets/
# Include current and future approved WebP assets, while nginx restricts public paths.
COPY assets/*.webp /usr/share/nginx/html/assets/
{{localized_copies}}
USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
