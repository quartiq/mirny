def main():
    from mirny_cpld import Platform
    from mirny import Mirny

    p = Platform()
    mirny = Mirny(p)
    p.build(mirny, build_name="mirny", mode="cpld")


if __name__ == "__main__":
    main()
