from invoke import task

@task
def unit(c):
    print("Running unit tests!")

@task
def integration(c):
    print("Running integration tests!")