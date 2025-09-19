FROM node:20-alpine

WORKDIR /usr/src/app

COPY package.json /usr/src/app/package.json
# Si existiera lockfile, cópialo para aprovechar caché
# COPY package-lock.json /usr/src/app/package-lock.json

RUN npm install

COPY . /usr/src/app

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "--port", "5173"]

