from locust import HttpUser, TaskSet, task, between


class RedirectTasks(TaskSet):
    @task
    def redirect_test(self):
        with self.client.get("/links/myalias", allow_redirects=False, catch_response=True) as response:
            if response.status_code == 301:
                response.success()
            else:
                response.failure(f"Expected 301, got {response.status_code}")


class WebsiteUser(HttpUser):
    tasks = [RedirectTasks]
    wait_time = between(1, 3)
