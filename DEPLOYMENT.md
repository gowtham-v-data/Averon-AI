# Averon AI - Deployment Guide

This guide will help you deploy the Averon AI application to get a live URL.

## Architecture
- **Frontend**: React + Vite (Deploy to Vercel)
- **Backend**: FastAPI + Python (Deploy to Render)

---

## 🚀 Backend Deployment (Render)

### Step 1: Create a Render Account
1. Go to [render.com](https://render.com)
2. Sign up with your GitHub account

### Step 2: Deploy Backend
1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repository: `gowtham-v-data/Averon-AI`
3. Configure the service:
   - **Name**: `averon-ai-backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free

### Step 3: Add Environment Variables
In Render dashboard, add these environment variables:
- `GROQ_API_KEY` = Your Groq API key
- `PINECONE_API_KEY` = Your Pinecone API key
- `PINECONE_INDEX_NAME` = Your Pinecone index name
- `DATABASE_URL` = Your PostgreSQL connection string

### Step 4: Deploy
1. Click **"Create Web Service"**
2. Wait for deployment to complete
3. Copy your backend URL (e.g., `https://averon-ai-backend.onrender.com`)

---

## 🎨 Frontend Deployment (Vercel)

### Step 1: Update API URL
1. Open `frontend/src/App.jsx`
2. Change line 5 from:
   ```javascript
   const API_BASE = 'http://127.0.0.1:8000';
   ```
   to:
   ```javascript
   const API_BASE = 'https://your-backend-url.onrender.com';
   ```

### Step 2: Deploy to Vercel
1. Go to [vercel.com](https://vercel.com)
2. Sign up with your GitHub account
3. Click **"Add New Project"**
4. Import `gowtham-v-data/Averon-AI`
5. Configure:
   - **Root Directory**: `frontend`
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
6. Click **"Deploy"**

### Step 3: Get Your Live URL
- Vercel will provide a URL like: `https://averon-ai.vercel.app`
- This is your live application URL!

---

## 🔧 Alternative: Quick Deploy with One Click

### Option A: Deploy Backend to Railway
1. Go to [railway.app](https://railway.app)
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select `gowtham-v-data/Averon-AI`
4. Railway will auto-detect Python and deploy
5. Add environment variables in Settings

### Option B: Deploy Frontend to Netlify
1. Go to [netlify.com](https://netlify.com)
2. Click **"Add new site"** → **"Import from Git"**
3. Select your repository
4. Configure:
   - **Base directory**: `frontend`
   - **Build command**: `npm run build`
   - **Publish directory**: `frontend/dist`

---

## ✅ Verification

After deployment:
1. Visit your frontend URL
2. Test the chat functionality
3. Test file upload
4. Test voice features
5. Check that all API calls work

---

## 🐛 Troubleshooting

### Backend Issues
- Check Render logs for errors
- Verify all environment variables are set
- Ensure PostgreSQL database is accessible

### Frontend Issues
- Verify API_BASE URL is correct
- Check browser console for CORS errors
- Ensure backend is running and accessible

### Database Issues
- Use Render's free PostgreSQL addon
- Or use a cloud database like Supabase or Neon

---

## 📝 Notes

- Free tier limitations:
  - Render: May sleep after inactivity (cold starts)
  - Vercel: 100GB bandwidth/month
- For production: Upgrade to paid plans for better performance
- Remember to keep your API keys secure and never commit `.env` files

---

## 🎉 Success!

Your Averon AI application should now be live!
- Frontend: `https://your-app.vercel.app`
- Backend: `https://your-backend.onrender.com`

Share your live URL and enjoy! 🚀
