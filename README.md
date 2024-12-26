Önce aws konsolde bir amazon linux 2023 makine ayağa kaldıralım.
burada hem makineye ssh ile bağlanmak hemde kendi uygulamamızı görebilmek için security grup ayarlarından 22 ve 8080 portlarını açık olmasını unutmayalım

sonra makineye ssh ile bağlandık.
projeyi yazmak için "konzek" adında bir folder oluşturup içine geçelim.

```
mkdir konzek && cd konzek
```

python yüklü olmadığı için önce makineye python yükleyelim.

```
sudo dnf update -y
sudo dnf install python3 -y
python3 --version
```
çıktı ---> Python 3.9.20

app.py dosyasını oluşturduk

```
from http.server import SimpleHTTPRequestHandler, HTTPServer

host = "0.0.0.0"
port = 8080

class CustomHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Hello, World!")

if __name__ == "__main__":
    with HTTPServer((host, port), CustomHandler) as server:
        print(f"Server running on {host}:{port}")
        server.serve_forever()
```

8080 portundan "Hello, World!" yazan bir sayfa gösteren basit bir kod yazdık.
uygulamayı çalıştırıp denedik,

```
python3 app.py
ps aux | grep python
```
çıktı:

ec2-user    3681  0.0  0.2 222316  2052 pts/1    S+   19:58   0:00 grep --color=auto python

systemd unit dosyası yazalım.
Uygulamanın bir systemd servisi olarak çalışması için bir ".service" dosyası oluşturalım.

```
# /etc/systemd/system/myapp.service
[Unit]
Description=My Simple Python HTTP Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/ec2-user/konzek/app.py
WorkingDirectory=/home/ec2-user/konzek
Restart=always
StandardOutput=file:/var/log/myapp.log
StandardError=file:/var/log/myapp_error.log

[Install]
WantedBy=multi-user.target
```
Servisi etkinleştirip ve başlatalım;

```
sudo systemctl daemon-reload
sudo systemctl enable myapp.service
sudo systemctl start myapp.service
```

servisin durumunu kontrol edelim,

```
sudo systemctl status myapp.service
```
ve "http://<server_ip>:8080" adresinden uygulamanın çalıştığını doğrulayalım.

çalıştığını gördüysek docker ile servis etmeye geçmeden 8080 de çakışma olmaması için durduralım  
```
sudo systemctl stop myapp.service
```


2. AŞAMAYA GEÇELİM
Server'a docker yükleyelim
```
sudo yum update -y
sudo yum install docker -y

sudo systemctl start docker
sudo systemctl enable docker

sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

docker --version
docker-compose --version
```
docker ve docker-compose yükledik

Dockerfile oluşturalım

```
FROM python:3.9-slim

WORKDIR /app

COPY app.py .

CMD ["python", "app.py"]
```
compose file oluşturalım
docker-compose.yml
```
version: '3.8'

services:
  app:
    image: myapp:latest
    build:
      context: .
    ports:
      - "8080" # Sadece dahili erişim için, harici port belirtmeye gerek yok
    restart: always
    networks:
      - app-network

  reverse-proxy:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

```

nginx.conf dosyası oluşturalım
```
events {}

http {
  upstream app_servers {
  server dockerlar-app-1:8080 max_fails=3 fail_timeout=30s;
  server dockerlar-app-2:8080 max_fails=3 fail_timeout=30s;
}


  server {
    listen 80;

    location / {
      proxy_pass http://app_servers;
    }
  }
}


```
Nginx, bir backend konteyner çalışmıyorsa onu kullanmayı otomatik olarak durdurur. Ancak, bunu anlaması için bir sağlık kontrolü (health check) yapılandırabilirsiniz. Örneğin:

```
`upstream app_servers {
  server dockerlar-app-1:8080 max_fails=3 fail_timeout=30s;
  server dockerlar-app-2:8080 max_fails=3 fail_timeout=30s;
}
```
Bu durumda, bir konteyner üç kez başarısız yanıt verirse (örneğin HTTP 5xx), Nginx bu konteyneri geçici olarak listeden çıkarır.

uygulamayı 80 portundan göreceğiz ancak her iki containerda load balance yaptığını test 
edebilmek için app.py uygulamamıza "hello world" yazısı ile beraber container hostname yazacak şekilde düzenleyelim,


```
from http.server import SimpleHTTPRequestHandler, HTTPServer
import socket

host = "0.0.0.0"
port = 8080

class CustomHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        hostname = socket.gethostname()  # Container'ın hostname'ini al
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(f"Hello, World from {hostname}!".encode())  # Yanıt mesajına hostname ekle

if __name__ == "__main__":
    with HTTPServer((host, port), CustomHandler) as server:
        print(f"Server running on {host}:{port}")
        server.serve_forever()
```

app.py güncelledik yeni build alalım

```
docker-compose build
docker-compose up -d --scale app=2
```
reverse proxy test edelim ;

```
curl http://localhost
```
Hello, World from 874663d5beb8! 
```
curl http://localhost
```
Hello, World from 0c452658dce4!

Bu mimaride iki adet container da aynı sayfayı görecek şekilde bir yapı oluşturduk, gelen istekler "round-robin" yük dengele yöntemi kullanılarak yönlendirilir, ek olarak herhangi bir container çökerse ve 3 başarısız yanıt verirse geçii olarak listeden çıkartarak kullanıcının çöken container'a yönlendirilmesinin önüne geçtik.

3 AŞAMA KUBERNETES DEPLOY

Kubernetes ortamı için ben uzak sunucuda kubeadm ile kurduğum cluster'ı kullanacağım.ingress kullanacağım için domain yönlendirmesi yapabilmek için de Metallb kuracağım, hadi başlayalım.

manifesto dosyalarını oluşturalım app-deployment.yaml:
```
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deployment
  labels:
    app: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: app
        image: emredochub/myapp
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "64Mi"
            cpu: "250m"
          limits:
            memory: "128Mi"
            cpu: "500m"
      imagePullSecrets:
      - name: my-docker-secret

```
app-service.yaml:
```
apiVersion: v1
kind: Service
metadata:
  name: app-service
spec:
  selector:
    app: myapp
  ports:
  - protocol: TCP
    port: 80         # Cluster içindeki port
    targetPort: 8080 # Pod'un dinlediği port
  type: LoadBalancer

```
app-ingress.yaml:
```
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
    nginx.ingress.kubernetes.io/use-proxy-protocol: "false"
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - host: kon.emredevops.click # Alan adınız
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: app-service
            port:
              number: 80

```
metalLB kurmak için önce 

```
kubectl edit configmap -n kube-system kube-proxy
```
komutu sonrası stricARP true yapılır ve kaydedilir.

sonra metallb kurulur
```
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.9/config/manifests/metallb-native.yaml
```
metallb için metallb-onfig.yaml:

```
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: my-ip-pool
  namespace: metallb-system
spec:
  addresses:
  - <server-ip>-<server-ip>  # Sunucunuzun IP adresi
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: my-advertisement
  namespace: metallb-system
spec: {}
```
burada biz tek bir node üzerinde kubernetes kurduğumuz için ip adres olarak server ip'yi adres satırında sadece tek ip olacak şekilde ayarladık.

kubernetes'in imageları dockerhub'dan çekebilmesi için secret oluşturmalıyız:
```
kubectl create secret docker-registry my-docker-secret \
  --docker-username=<usernme> \
  --docker-password=<password> \
  --docker-email=<email>

```
bütün dosyaları çalıştıralım :
```
kubectl apply -f .
```
deneyelim :
```
curl kon.emredevops.click

Hello, World from app-deployment-55d4bc9dc9-q9gjf!

curl kon.emredevops.click

Hello, World from app-deployment-55d4bc9dc9-wfdml!

```

çıktıdan görebildiğimiz gibi her yenilemede farklı pod'a yönlenme sağlıyoruz.

Şimdi de herhangi bir değişiklikte yeni image'ları deploy edebilmek için yapmamız gerekenleri yani "Rolling update" işlemlerine geçelim:

Öncesinde uygulama kodunda bir değişiklik olduğunu ve bu değişiklik ile yeni imageları docker hub'a yolladığımızı kabul ediyorum ve yeni image ismi olarak da "emredochub/myapp:v2" yaptık diyelim.

Hatta bu süreç içinde bir CI/CD tool kullanarak (örneğin Jenkis) github gibi bir registeryden kodda değişiklik olursa tetiklenecek bir pipeline ile yeni imageları docker hub'a yollayacak bir sistem de kurulabilir, bu da yine DevOps kültüründe çok kullanılan bir mimaridir.


bu sefer image değişikliğini imperative değil declerative olarak yapalım:

```
kubectl set image deployment/my-app my-app-container=akimmetal/myapp:v2
```
bu komut ile deploymentta'ki image version:2 ile değiştirilecek,kontrol edelim,
ben anlaşılması için uygulamamın başına "2---hello world" şeklinde bir ekleme yaptım.

burada ek olarak deploymentımızın stratejisini "rolling update" veya "recreate" belirleyebiliriz

bunun için ek olarak deploymantta ilgili yere:
```
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1  # Aynı anda devre dışı kalacak maksimum pod sayısı
      maxSurge: 1        # Ek olarak başlatılacak maksimum pod sayısı
```
satırını ekliyoruz.

Her seferinde maksimum 1 pod durdurulacak
Aynı anda maksimum 1 yeni pod başlatılacak

recreate seçseydik:
```
spec:
  strategy:
    type: Recreate
```
Mevcut pod'lar tamamen durdurulur.
Yeni pod'lar başlatılmaya başlanır.

güncellemeyi doğrulayalım:
```
kubectl rollout status deployment/app-deployment
deployment "app-deployment" successfully rolled out
```

değişiklikleri kontrol edelim
```
curl kon.emredevops.click
2---Hello, World from app-deployment-8c748c75b-hlz72!
curl kon.emredevops.click
2---Hello, World from app-deployment-8c748c75b-ql6d8!
```

Gördüğünüz gibi load balancing çalışıyor ve yeni uygulamamız sağlıklı şekilde deploy edilmiş.

Son olarak ben burada genel olarak basit bir mimari üzerinden örnekler verdim daha büyük ve güvenlik ayarları yapılan mimarilerde hem kodlama tarafında hemde kubernetes ve docker tarafında yapılacak ek işlemler ile mimari daha sağlıklı hale getirilebilir.
