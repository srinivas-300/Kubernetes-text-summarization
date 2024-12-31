# Kubernetes-text-summarization

Project about Key Information extraction from Research Documents.

## Here are the deployment steps on Google Cloud Platform
```
gcloud builds --project <your-project-id>     submit --tag gcr.io/<your-project-id>/flask-app:latest .

gcloud container clusters create my-cluster   --zone us-central1-a   --num-nodes 2
gcloud container clusters get-credentials my-cluster --zone us-central1-a

kubectl create secret generic google-cloud-key-secret --from-file=key.json=flaskstoragekey.json

kubectl apply -f app.yaml
kubectl expose deployment flask-app-tutorial \
--type=LoadBalancer --port 80 --target-port 8080
kubectl get services -l name=flask-app-tutorial

### Deleting the cluster
gcloud container clusters delete my-cluster --zone us-central1-a
```

For deployment you will need a service account of the google cloud , google api token from google generative ai site and mongodb credentials.


References:
Deployment guide: [A Guide to Deploy Flask App on Google Kubernetes Engine](https://medium.com/@pyk/a-guide-to-deploy-flask-app-on-google-kubernetes-engine-bfbbee5c6fb)

