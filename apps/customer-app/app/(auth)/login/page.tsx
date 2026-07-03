import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import LoginForm from "@/components/auth/LoginForm";

export default async function LoginPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (token) redirect("/dashboard");

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 bg-gray-50/60">
      <LoginForm />
    </div>
  );
}
